"""Repository for ``pieces`` and the world-space layout helpers.

Pieces now carry an absolute pose ``(x, y, rot)`` (rot in 30-degree steps).
Connections between pieces are no longer stored — they are derived from
coincident world endings on every render via :func:`layouts_connections`.
"""

from ..extensions import sql
from ..services.geometry import SNAP_TOLERANCE, transform_for_pose


def pieces_update(track_id, pieces):
    """Replace all pieces for a track.

    ``pieces`` is a list of dicts with keys ``type``, ``x``, ``y``, ``rot``.
    Returns the list of newly assigned piece ids in insertion order.
    """
    sql("delete from pieces where track_id = :track_id", track_id=track_id)
    new_ids = []
    for p in pieces:
        sql(
            "insert into pieces (track_id, piece, x, y, rot)"
            " values (:track_id, :piece, :x, :y, :rot)",
            track_id=track_id,
            piece=p["type"],
            x=float(p["x"]),
            y=float(p["y"]),
            rot=int(p["rot"]),
        )
        # Last inserted id (sqlite + mysql both support this).
        row = sql("select max(id) as mid from pieces where track_id = :track_id",
                  track_id=track_id)
        new_ids.append(row[0]["mid"])
    return new_ids


def piece_insert(track_id, piece_type, x, y, rot):
    """Insert a single piece, return its new id."""
    sql(
        "insert into pieces (track_id, piece, x, y, rot)"
        " values (:track_id, :piece, :x, :y, :rot)",
        track_id=track_id, piece=piece_type,
        x=float(x), y=float(y), rot=int(rot),
    )
    row = sql("select max(id) as mid from pieces where track_id = :track_id",
              track_id=track_id)
    return row[0]["mid"]


def piece_update_pose(track_id, piece_id, x, y, rot):
    sql(
        "update pieces set x = :x, y = :y, rot = :rot"
        " where id = :pid and track_id = :track_id",
        x=float(x), y=float(y), rot=int(rot),
        pid=int(piece_id), track_id=track_id,
    )


def piece_delete(track_id, piece_id):
    sql(
        "delete from pieces where id = :pid and track_id = :track_id",
        pid=int(piece_id), track_id=track_id,
    )


def pieces_read(track_id):
    """Return ``[{id, type, x, y, rot}, ...]`` ordered by id."""
    rows = sql(
        "select id, piece, x, y, rot from pieces"
        " where track_id = :track_id order by id",
        track_id=track_id,
    )
    return [
        {"id": r["id"], "type": r["piece"],
         "x": float(r["x"]), "y": float(r["y"]), "rot": int(r["rot"])}
        for r in rows
    ]


def layouts_parse(track_id):
    """Compatibility shim: returns the same list as :func:`pieces_read`."""
    return pieces_read(track_id)


def pieces_read_all():
    return sql("select * from pieces")


def layouts_build(pieces):
    """Compute world geometry for all pieces.

    Returns ``(pathes, all_endings, centerlines_per_piece)`` where
      * ``pathes[i]``                  — list of ``{'x','y'}``
      * ``all_endings[piece_id]``      — list of ending pairs (world coords)
      * ``centerlines_per_piece[i]``   — list of polylines (each list of {x,y})

    Iteration order matches ``pieces`` (i.e. piece-id order from
    :func:`pieces_read`).
    """
    pathes = []
    centerlines_per_piece = []
    all_endings = {}
    for p in pieces:
        pts, eds, cls = transform_for_pose(p["type"], p["x"], p["y"], p["rot"])
        pathes.append(pts)
        centerlines_per_piece.append(cls)
        all_endings[p["id"]] = eds
    return pathes, all_endings, centerlines_per_piece


def _pairs_fit(pair_a, pair_b, tolerance):
    """True if two ending pairs coincide face-to-face within ``tolerance``.

    Connection rule: pieces meet face-to-face, so the second ending's points
    are reversed relative to the first. We use the same Manhattan-style
    metric as the original ``fitting()`` (sum of |dx| + |dy|), scaled to the
    tolerance.
    """
    (a1, a2) = pair_a
    (b1, b2) = pair_b
    res = (abs(a1[0] - b2[0]) + abs(a1[1] - b2[1])
           + abs(a2[0] - b1[0]) + abs(a2[1] - b1[1]))
    return res < tolerance


def layouts_connections(all_endings, tolerance=None):
    """Derive connections from coincident world endings.

    Returns a list of ``((piece_id_a, ending_idx_a), (piece_id_b, ending_idx_b))``
    pairs. Each ending appears in at most one connection (the closest one
    wins if multiple candidates would match).
    """
    tol = SNAP_TOLERANCE if tolerance is None else tolerance
    flat = []
    for pid, eds in all_endings.items():
        for eidx, pair in enumerate(eds):
            flat.append((pid, eidx, pair))

    used = set()
    connections = []
    for i in range(len(flat)):
        if (flat[i][0], flat[i][1]) in used:
            continue
        for j in range(i + 1, len(flat)):
            if flat[i][0] == flat[j][0]:
                continue  # never connect a piece to itself
            if (flat[j][0], flat[j][1]) in used:
                continue
            if _pairs_fit(flat[i][2], flat[j][2], tol):
                connections.append(((flat[i][0], flat[i][1]),
                                    (flat[j][0], flat[j][1])))
                used.add((flat[i][0], flat[i][1]))
                used.add((flat[j][0], flat[j][1]))
                break
    return connections


def layouts_free_endings(all_endings, connections=None, tolerance=None):
    """Return the list of ``(piece_id, ending_idx)`` not consumed by any
    connection.

    If ``connections`` is ``None`` it is computed from ``all_endings`` itself.
    """
    if connections is None:
        connections = layouts_connections(all_endings, tolerance=tolerance)
    consumed = set()
    for (a, b) in connections:
        consumed.add(a)
        consumed.add(b)
    free = []
    for pid, eds in all_endings.items():
        for eidx in range(len(eds)):
            if (pid, eidx) not in consumed:
                free.append((pid, eidx))
    return free
