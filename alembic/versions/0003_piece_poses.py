"""Independent pieces with absolute poses.

Replaces the chained-tree representation with absolute ``(x, y, rot)`` poses
on every piece, where ``rot`` is in 30-degree steps (0..11).

Schema changes
--------------
* ``pieces``  + columns ``x FLOAT``, ``y FLOAT``, ``rot INT``; drop unused
  ``idx`` column. ``pieces.id`` is now the public piece identifier.
* ``connections`` table dropped. Connections are derived at render time from
  coincident ending positions.
* ``editor_states``: drop ``connections_json`` and ``cursor_idx``; add
  ``selection_json`` (nullable) holding ``{"piece_id": int, "ending_idx": int|null}``.

Data backfill
-------------
For each existing track we replay the legacy chain (using ``track_types`` shape
data + an inline affine helper) to derive each piece's world pose, then write
``x/y/rot`` per row. ``editor_states`` is wiped — any in-progress autosave is
reloaded from the freshly migrated ``pieces`` table on next visit.

Revision ID: 0003_piece_poses
Revises: 0002_editor_states
Create Date: 2026-04-24
"""
from collections import defaultdict
from math import atan2, cos, pi, sin

from alembic import op
import sqlalchemy as sa


revision = "0003_piece_poses"
down_revision = "0002_editor_states"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------- inline math
# Self-contained replay of the legacy chain so this migration does not depend
# on the post-migration shape of duplo.services.geometry.

from duplo.services.track_types import (  # noqa: E402  (intentional after revision metadata)
    crossing,
    curve,
    straight,
    switch,
    zero_position,
)

_LOCAL_POINTS = {}
_LOCAL_ENDINGS = {}
_LOCAL_POINTS["straight"], _LOCAL_ENDINGS["straight"] = straight()
_LOCAL_POINTS["curve"], _LOCAL_ENDINGS["curve"] = curve()
_LOCAL_POINTS["switch"], _LOCAL_ENDINGS["switch"] = switch()
_LOCAL_POINTS["crossing"], _LOCAL_ENDINGS["crossing"] = crossing()

# Re-center each piece type so (0,0) is the piece centroid. Must match the
# convention used by duplo.services.geometry and static/js/track_edit.js.
for _t in ("straight", "curve", "switch", "crossing"):
    _xs = [p[0] for p in _LOCAL_POINTS[_t]]
    _ys = [p[1] for p in _LOCAL_POINTS[_t]]
    _px, _py = sum(_xs) / len(_xs), sum(_ys) / len(_ys)
    _LOCAL_POINTS[_t] = [(p[0] - _px, p[1] - _py) for p in _LOCAL_POINTS[_t]]
    _LOCAL_ENDINGS[_t] = [
        [(p[0] - _px, p[1] - _py) for p in e] for e in _LOCAL_ENDINGS[_t]
    ]


def _det3(a, b, c, d, e, f, g, h, i):
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def _solve3(matrix, rhs):
    (a, b, c), (d, e, f), (g, h, i) = matrix
    r0, r1, r2 = rhs
    det = _det3(a, b, c, d, e, f, g, h, i)
    x = _det3(r0, b, c, r1, e, f, r2, h, i) / det
    y = _det3(a, r0, c, d, r1, f, g, r2, i) / det
    z = _det3(a, b, r0, d, e, r1, g, h, r2) / det
    return x, y, z


def _affine_trafo(original, transform):
    (x1, y1), (x2, y2) = original
    (x1p, y1p), (x2p, y2p) = transform
    x3 = x1 + y1 - y2
    y3 = y1 + x2 - x1
    x3p = x1p + y1p - y2p
    y3p = y1p + x2p - x1p
    matrix = [[x1, y1, 1], [x2, y2, 1], [x3, y3, 1]]
    ax, bx, cx = _solve3(matrix, [x1p, x2p, x3p])
    ay, by, cy = _solve3(matrix, [y1p, y2p, y3p])

    def fn(p):
        return (ax * p[0] + bx * p[1] + cx, ay * p[0] + by * p[1] + cy)

    return fn


def _legacy_world_endings(types, connections):
    """Replay the chain. Returns ``{piece_idx: [ending_pair, ...]}``."""
    world = {-1: [zero_position()]}
    by_p2 = {c["p2"]: c for c in connections}
    for idx, ptype in enumerate(types):
        c = by_p2[idx]
        cursor = world[c["p1"]][c["e1"]][::-1]  # flipped, matching add_piece
        local_e = _LOCAL_ENDINGS[ptype][c["e2"]]
        trafo = _affine_trafo(local_e, cursor)
        world[idx] = [[trafo(p) for p in e] for e in _LOCAL_ENDINGS[ptype]]
    return world


def _pose_from_world_ending(ptype, world_ending_0):
    """Recover ``(x, y, rot_steps)`` from the world coords of local ending 0."""
    L1, L2 = _LOCAL_ENDINGS[ptype][0]
    W1, W2 = world_ending_0
    dlx, dly = (L2[0] - L1[0]), (L2[1] - L1[1])
    dwx, dwy = (W2[0] - W1[0]), (W2[1] - W1[1])
    angle = atan2(dwy, dwx) - atan2(dly, dlx)
    # Quantise to nearest 30 degrees
    rot_steps = round(angle / (pi / 6)) % 12
    qa = rot_steps * pi / 6
    ca, sa_ = cos(qa), sin(qa)
    # (x, y) = W1 - R(angle) * L1
    x = W1[0] - (ca * L1[0] - sa_ * L1[1])
    y = W1[1] - (sa_ * L1[0] + ca * L1[1])
    return float(x), float(y), int(rot_steps)


# ----------------------------------------------------------------- migration

def upgrade() -> None:
    conn = op.get_bind()

    # --- 1. read legacy data BEFORE schema change ---------------------------
    legacy_pieces = list(conn.execute(sa.text(
        "SELECT id, track_id, idx, piece FROM pieces"
    )).mappings())
    legacy_conns = list(conn.execute(sa.text(
        "SELECT track_id, p1, e1, p2, e2 FROM connections"
    )).mappings())

    pieces_by_track = defaultdict(list)
    for r in legacy_pieces:
        pieces_by_track[r["track_id"]].append(dict(r))
    conns_by_track = defaultdict(list)
    for r in legacy_conns:
        conns_by_track[r["track_id"]].append(
            {"p1": r["p1"], "e1": r["e1"], "p2": r["p2"], "e2": r["e2"]}
        )

    # Compute pose for each existing piece row, keyed by the row's primary id.
    poses = {}
    for track_id, rows in pieces_by_track.items():
        rows.sort(key=lambda r: r["idx"])
        types = [r["piece"] for r in rows]
        try:
            world = _legacy_world_endings(types, conns_by_track.get(track_id, []))
        except Exception:
            # Corrupt / orphaned chain — leave default (0,0,0); user will see
            # pieces stacked at the origin and can drag them apart.
            continue
        for r in rows:
            ends = world.get(r["idx"])
            if not ends:
                continue
            poses[r["id"]] = _pose_from_world_ending(r["piece"], ends[0])

    # --- 2. schema changes --------------------------------------------------
    with op.batch_alter_table("pieces") as batch:
        batch.add_column(sa.Column("x", sa.Float, nullable=False, server_default="0"))
        batch.add_column(sa.Column("y", sa.Float, nullable=False, server_default="0"))
        batch.add_column(sa.Column("rot", sa.Integer, nullable=False, server_default="0"))
        batch.drop_column("idx")

    op.drop_table("connections")

    with op.batch_alter_table("editor_states") as batch:
        batch.drop_column("connections_json")
        batch.drop_column("cursor_idx")
        batch.add_column(sa.Column("selection_json", sa.Text, nullable=True))

    # --- 3. backfill --------------------------------------------------------
    for piece_id, (x, y, rot) in poses.items():
        conn.execute(
            sa.text("UPDATE pieces SET x = :x, y = :y, rot = :rot WHERE id = :id"),
            {"x": x, "y": y, "rot": rot, "id": piece_id},
        )

    # editor_states rows with the old shape are no longer loadable.
    conn.execute(sa.text("DELETE FROM editor_states"))


def downgrade() -> None:
    # Lossy: rot/x/y are dropped, the chain is gone, connections cannot be
    # reconstructed without geometric heuristics. Recreate empty structures so
    # the schema matches 0002 again, but data is not preserved.
    with op.batch_alter_table("editor_states") as batch:
        batch.drop_column("selection_json")
        batch.add_column(sa.Column("connections_json", sa.Text, nullable=False, server_default="[]"))
        batch.add_column(sa.Column("cursor_idx", sa.Integer, nullable=False, server_default="0"))

    op.create_table(
        "connections",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "track_id",
            sa.Integer,
            sa.ForeignKey("tracks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("p1", sa.Integer, nullable=False),
        sa.Column("e1", sa.Integer, nullable=False),
        sa.Column("p2", sa.Integer, nullable=False),
        sa.Column("e2", sa.Integer, nullable=False),
    )

    with op.batch_alter_table("pieces") as batch:
        batch.add_column(sa.Column("idx", sa.Integer, nullable=False, server_default="0"))
        batch.drop_column("rot")
        batch.drop_column("y")
        batch.drop_column("x")
