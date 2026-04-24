"""Track piece geometry: lookup tables, pose transforms, snap helper.

Each piece has an absolute pose ``(x, y, rot)`` where ``rot`` is an integer
number of 30-degree steps (0..11). :func:`transform_for_pose` produces the
piece's world-space points, endings, and centerlines from a pose.
:func:`snap_pose` finds the pose that snaps a dragged piece's chosen ending
onto the nearest free ending of any other piece.
"""

from math import atan2, cos, pi, sin

from .track_types import c0, crossing, curve, l0, straight, switch, w0


points = {}
endings = {}

PIECE_TYPES = ['straight', 'curve', 'switch', 'crossing']

points['straight'], endings['straight'] = straight()
points['curve'],    endings['curve']    = curve()
points['switch'],   endings['switch']   = switch()
points['crossing'], endings['crossing'] = crossing()

# Centerlines: list of polylines (each a list of (x,y) tuples) that the
# train follows for each piece type, in piece-local coordinates.
_n_cl = 12
_cl_curve = [(c0 * cos(i * pi / 6 / (_n_cl - 1)), c0 * sin(i * pi / 6 / (_n_cl - 1))) for i in range(_n_cl)]
_cl_curve_mirrored = [(2 * c0 - p[0], p[1]) for p in _cl_curve]

centerlines = {
    'straight': [[(w0 / 2, i * l0 / (_n_cl - 1)) for i in range(_n_cl)]],
    'curve':    [_cl_curve],
    'switch':   [_cl_curve, _cl_curve_mirrored],
    'crossing': [
        [(0, -l0 / 2), (0, l0 / 2)],
        [(-l0 / 2 * sin(pi / 3), -l0 / 2 * cos(pi / 3)),
         (l0 / 2 * sin(pi / 3), l0 / 2 * cos(pi / 3))],
    ],
}

# Re-center each piece type so the local origin (0,0) sits at the centroid
# of the piece's outline. With this convention rotation pivots around the
# piece's visible center, and the stored pose ``(x, y)`` is the world
# position of that center. Mirrored on the JS side (LOCAL.* in
# track_edit.js) and inside alembic 0003 backfill — keep all three in sync.
pivots = {}
for _t in PIECE_TYPES:
    _xs = [p[0] for p in points[_t]]
    _ys = [p[1] for p in points[_t]]
    pivots[_t] = (sum(_xs) / len(_xs), sum(_ys) / len(_ys))
    _px, _py = pivots[_t]
    points[_t] = [(p[0] - _px, p[1] - _py) for p in points[_t]]
    endings[_t] = [[(p[0] - _px, p[1] - _py) for p in e] for e in endings[_t]]
    centerlines[_t] = [[(p[0] - _px, p[1] - _py) for p in cl] for cl in centerlines[_t]]

# Number of endings per piece type.
ending_count = {p: len(endings[p]) for p in PIECE_TYPES}

# Snap tolerance in world units. Two endings closer than this on commit will
# be considered connected. Roughly half a piece width; fits the previous
# inline tolerance of ~10 used by ``layouts_free_endings.fitting``.
SNAP_TOLERANCE = 0.6 * w0


def to_path(xy):
    return [{'x': x, 'y': y} for x, y in xy]


def _rotate(p, ca, sa):
    return (ca * p[0] - sa * p[1], sa * p[0] + ca * p[1])


def transform_for_pose(piece_type, x, y, rot_steps):
    """Apply pose ``(x, y, rot_steps)`` to a piece's local geometry.

    Returns ``(points_path, world_endings, centerlines_paths)``:
      * ``points_path``       — list of ``{'x','y'}``
      * ``world_endings``     — list of pairs ``[[x1,y1],[x2,y2]]``
      * ``centerlines_paths`` — list of polylines, each list of ``{'x','y'}``
    """
    angle = (int(rot_steps) % 12) * pi / 6
    ca, sa = cos(angle), sin(angle)
    x = float(x)
    y = float(y)

    def trafo(p):
        rx, ry = _rotate(p, ca, sa)
        return [rx + x, ry + y]

    pts = [trafo(p) for p in points[piece_type]]
    eds = [[trafo(p) for p in e] for e in endings[piece_type]]
    cls = [to_path([trafo(p) for p in cl]) for cl in centerlines[piece_type]]
    return to_path(pts), eds, cls


def world_endings_for_pose(piece_type, x, y, rot_steps):
    """Cheaper variant: only the world-space endings (used by snap previews)."""
    angle = (int(rot_steps) % 12) * pi / 6
    ca, sa = cos(angle), sin(angle)
    x = float(x)
    y = float(y)

    def trafo(p):
        rx, ry = _rotate(p, ca, sa)
        return (rx + x, ry + y)

    return [[trafo(p) for p in e] for e in endings[piece_type]]


def _ending_midpoint(end_pair):
    return ((end_pair[0][0] + end_pair[1][0]) * 0.5,
            (end_pair[0][1] + end_pair[1][1]) * 0.5)


def _pose_to_align(piece_type, anchor_ending_idx, target_pair):
    """Return ``(x, y, rot_steps)`` such that the dragged piece's anchor
    ending overlays ``target_pair`` reversed.

    Connection rule: pieces meet face-to-face, so ending pairs are reversed
    (p1.e1 = [A1, A2] world  <=>  p2.e2 = [A2, A1] world).
    """
    L1, L2 = endings[piece_type][anchor_ending_idx]
    T1, T2 = target_pair
    # Dragged anchor in world must be [T2, T1].
    dlx, dly = (L2[0] - L1[0]), (L2[1] - L1[1])
    dwx, dwy = (T1[0] - T2[0]), (T1[1] - T2[1])
    angle = atan2(dwy, dwx) - atan2(dly, dlx)
    rot_steps = round(angle / (pi / 6)) % 12
    qa = rot_steps * pi / 6
    ca, sa_ = cos(qa), sin(qa)
    # (x, y) = T2 - R(qa) * L1
    x = T2[0] - (ca * L1[0] - sa_ * L1[1])
    y = T2[1] - (sa_ * L1[0] + ca * L1[1])
    return float(x), float(y), int(rot_steps)


def snap_pose(piece_type,
              anchor_ending_idx,
              current_pose,
              free_target_endings,
              tolerance=SNAP_TOLERANCE):
    """Find the closest snap target for a dragged piece.

    Parameters
    ----------
    piece_type : str
    anchor_ending_idx : int
        Which local ending of the dragged piece is the snap anchor.
    current_pose : (x, y, rot_steps)
        The dragged piece's current free pose.
    free_target_endings : list of dicts
        Each ``{"piece_id": int, "ending_idx": int, "pair": [[x1,y1],[x2,y2]]}``
        — the world-space free endings of *other* pieces. The caller must
        exclude the dragged piece's own endings.
    tolerance : float
        Maximum world distance between the dragged anchor's *current*
        midpoint and the target midpoint to accept the snap.

    Returns
    -------
    None or dict
        ``None`` if nothing snaps. Otherwise
        ``{"pose": (x, y, rot_steps),
           "target": {"piece_id": int, "ending_idx": int}}``.
    """
    cur_world = world_endings_for_pose(piece_type, *current_pose)[anchor_ending_idx]
    cur_mid = _ending_midpoint(cur_world)

    best = None
    best_dist = float("inf")
    tol2 = tolerance * tolerance
    for target in free_target_endings:
        tmid = _ending_midpoint(target["pair"])
        d_probe = (cur_mid[0] - tmid[0]) ** 2 + (cur_mid[1] - tmid[1]) ** 2
        if d_probe > tol2:
            continue
        pose = _pose_to_align(piece_type, anchor_ending_idx, target["pair"])
        if d_probe < best_dist:
            best_dist = d_probe
            best = {"pose": pose,
                    "target": {"piece_id": target["piece_id"],
                               "ending_idx": target["ending_idx"]}}
    return best
