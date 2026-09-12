"""Tests for the automatic track designer.

The designer is pure geometry and search, so most of this needs no Flask and
no DB. The important property throughout: a design is only correct if the
*editor* agrees it is closed, so the checks here go through the same
``layouts_connections`` the app uses at view time rather than trusting the
designer's own bookkeeping.
"""

import pytest

from duplo.repositories.layouts import layouts_build, layouts_connections, layouts_free_endings
from duplo.services.designer import (
    MAX_ADVANCE,
    ROUTES,
    UNITS_PER_M,
    _caps_variants,
    _count_reversals,
    design_track,
    score_layout,
)
from duplo.services.geometry import (
    PIECE_TYPES,
    can_force_connect,
    ending_count,
    ending_heading,
    endings_fit,
    polygons_overlap,
    world_polygon,
)

DEFAULT_LIB = {"straight": 8, "curve": 12, "switch": 2, "crossing": 1}


# --------------------------------------------------------------- piece model

def test_routes_cover_every_ending():
    """Every ending must be reachable, or a closed design could never use it."""
    for ptype, routes in ROUTES.items():
        touched = {e for route in routes for e in route}
        assert touched == set(range(ending_count[ptype])), ptype


def test_routes_are_reversible():
    for ptype, routes in ROUTES.items():
        for e_in, e_out in routes:
            assert (e_out, e_in) in routes, (ptype, e_in, e_out)


def test_every_piece_advances_the_track():
    for ptype in PIECE_TYPES:
        assert MAX_ADVANCE[ptype] > 0


def test_ending_heading_is_outward_and_opposite_across_a_joint():
    """A straight's two endings must point in opposite directions."""
    eds = [
        [(p["x"], p["y"]) for p in pair]
        for pair in _world_endings("straight", 0.0, 0.0, 0)
    ]
    h0 = ending_heading(eds[0])
    h1 = ending_heading(eds[1])
    assert (h0 - h1) % 12 == 6


def _world_endings(ptype, x, y, rot):
    from duplo.services.geometry import world_endings_for_pose
    return [[{"x": p[0], "y": p[1]} for p in pair]
            for pair in world_endings_for_pose(ptype, x, y, rot)]


# ------------------------------------------------------------------ variants

def test_switch_allowances_are_always_even():
    """A switch has three endings, so an odd number can never close."""
    for variant in _caps_variants({"straight": 8, "curve": 12,
                                   "switch": 3, "crossing": 2}):
        assert variant["switch"] % 2 == 0


def test_variants_offer_the_richest_allowance_first():
    """Switches and crossings are the point, so they get first crack."""
    variants = _caps_variants(DEFAULT_LIB)
    assert variants[0]["switch"] == (DEFAULT_LIB["switch"] // 2) * 2
    assert variants[0]["crossing"] == DEFAULT_LIB["crossing"]
    # ...and the plain allowance is still there as a fallback.
    assert {"switch": 0, "crossing": 0}.items() <= variants[-1].items()


# -------------------------------------------------------------------- scoring

def test_reversals_ignore_straights_and_count_direction_changes():
    assert _count_reversals([1, 1, 1, 1]) == 0          # a plain loop
    assert _count_reversals([1, 0, 1, 0, 1]) == 0       # straights don't count
    assert _count_reversals([1, -1, 1]) == 2            # an S and back
    assert _count_reversals([]) == 0


def test_score_prefers_the_more_interesting_of_two_equal_designs():
    room = 6 * UNITS_PER_M, 4 * UNITS_PER_M
    boring = _fake_placed([1] * 12 + [0] * 8)
    wiggly = _fake_placed([1] * 10 + [-1, 1] + [0] * 8)
    s_boring, _ = score_layout(boring, DEFAULT_LIB, *room)
    s_wiggly, _ = score_layout(wiggly, DEFAULT_LIB, *room)
    assert s_wiggly > s_boring


def _fake_placed(turns):
    """Minimal placed-piece dicts; only turn and bbox matter to the score."""
    return [
        {"type": "curve" if t else "straight", "turn": t,
         "lo_x": 0.0, "hi_x": 100.0, "lo_y": 0.0, "hi_y": 100.0}
        for t in turns
    ]


# ------------------------------------------------------- end-to-end designing

@pytest.fixture(scope="module")
def design():
    result = design_track(DEFAULT_LIB, room_w=6.0, room_h=4.0, seed=7,
                          time_budget=6.0)
    assert result is not None, "designer found nothing for the default library"
    return result


def test_design_uses_only_pieces_the_user_owns(design):
    used = {t: 0 for t in PIECE_TYPES}
    for piece in design["pieces"]:
        used[piece["type"]] += 1
    for ptype, n in used.items():
        assert n <= DEFAULT_LIB[ptype], ptype


def test_design_is_closed_according_to_the_editor(design):
    """The whole point: no ending may be left over.

    Closure is judged the way the editor judges it — a joint the designer
    deliberately left inside force-connection range counts as connected,
    because the editor records it as a forced connection.
    """
    pieces = [dict(p, id=i) for i, p in enumerate(design["pieces"])]
    _, all_endings, _ = layouts_build(pieces)
    free = set(layouts_free_endings(all_endings))
    for fc in design["forced"]:
        free.discard((fc["piece1"], fc["ending1_idx"]))
        free.discard((fc["piece2"], fc["ending2_idx"]))
    assert free == set()


def test_forced_joints_are_within_the_editors_tolerance(design):
    """Anything left open must actually be force-connectable."""
    pieces = [dict(p, id=i) for i, p in enumerate(design["pieces"])]
    _, all_endings, _ = layouts_build(pieces)
    for fc in design["forced"]:
        a = all_endings[fc["piece1"]][fc["ending1_idx"]]
        b = all_endings[fc["piece2"]][fc["ending2_idx"]]
        assert can_force_connect(a, b)["can_force"], fc


def test_design_is_one_connected_track(design):
    pieces = [dict(p, id=i) for i, p in enumerate(design["pieces"])]
    _, all_endings, _ = layouts_build(pieces)
    connections = layouts_connections(all_endings)

    adjacency = {p["id"]: set() for p in pieces}
    for (a, b) in connections:
        adjacency[a[0]].add(b[0])
        adjacency[b[0]].add(a[0])

    seen = {pieces[0]["id"]}
    stack = [pieces[0]["id"]]
    while stack:
        for neighbour in adjacency[stack.pop()]:
            if neighbour not in seen:
                seen.add(neighbour)
                stack.append(neighbour)
    assert len(seen) == len(pieces), "design falls into separate loops"


def test_design_has_no_overlapping_pieces(design):
    polys = [world_polygon(p["type"], p["x"], p["y"], p["rot"])
             for p in design["pieces"]]
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            assert not polygons_overlap(polys[i], polys[j]), (i, j)


def test_design_fits_in_the_room(design):
    xs, ys = [], []
    for p in design["pieces"]:
        for (x, y) in world_polygon(p["type"], p["x"], p["y"], p["rot"]):
            xs.append(x)
            ys.append(y)
    assert max(xs) - min(xs) <= 6.0 * UNITS_PER_M + 1e-6
    assert max(ys) - min(ys) <= 4.0 * UNITS_PER_M + 1e-6


def test_design_is_centred_on_the_origin(design):
    xs, ys = [], []
    for p in design["pieces"]:
        for (x, y) in world_polygon(p["type"], p["x"], p["y"], p["rot"]):
            xs.append(x)
            ys.append(y)
    assert (max(xs) + min(xs)) / 2 == pytest.approx(0.0, abs=1e-6)
    assert (max(ys) + min(ys)) / 2 == pytest.approx(0.0, abs=1e-6)


def test_rotations_are_whole_thirty_degree_steps(design):
    for p in design["pieces"]:
        assert p["rot"] == int(p["rot"]) and 0 <= p["rot"] < 12


def test_same_seed_gives_the_same_design():
    a = design_track(DEFAULT_LIB, seed=3, time_budget=2.0)
    b = design_track(DEFAULT_LIB, seed=3, time_budget=2.0)
    assert (a is None) == (b is None)
    if a is not None:
        assert a["pieces"] == b["pieces"]


def test_a_box_that_cannot_make_a_loop_returns_none():
    """A closed loop turns through 360 degrees, so it needs 12 curves."""
    assert design_track({"straight": 20, "curve": 4, "switch": 0,
                         "crossing": 0}, time_budget=2.0) is None


def test_curves_alone_make_the_plain_circle():
    result = design_track({"straight": 0, "curve": 12, "switch": 0,
                           "crossing": 0}, seed=1, time_budget=4.0)
    assert result is not None
    assert len(result["pieces"]) == 12


def test_room_size_is_respected_when_it_is_tight():
    """A room too small for any loop must not produce an oversized design."""
    result = design_track(DEFAULT_LIB, room_w=0.6, room_h=0.6, seed=2,
                          time_budget=3.0)
    if result is None:
        return
    xs, ys = [], []
    for p in result["pieces"]:
        for (x, y) in world_polygon(p["type"], p["x"], p["y"], p["rot"]):
            xs.append(x)
            ys.append(y)
    assert max(xs) - min(xs) <= 0.6 * UNITS_PER_M + 1e-6
    assert max(ys) - min(ys) <= 0.6 * UNITS_PER_M + 1e-6


# ----------------------------------------------------------- editor plumbing
#
# Only the empty-floor path lives here. ``autodesign`` on a floor that already
# has pieces on it *completes* rather than replaces, and is covered in
# test_completion.py against the real hand-built layouts.

def test_designed_layout_reports_closed_in_the_view_model(app, track_id):
    from duplo.services.editor import LayoutEditor
    with app.app_context():
        editor = LayoutEditor(track_id, [])
        assert editor.autodesign(DEFAULT_LIB, 6, 4, seed=5,
                                 time_budget=6.0) is not None
        view = editor.view_model(DEFAULT_LIB)
        assert view["is_closed"] is True
        assert all(not e["free"] for p in view["pieces"] for e in p["endings"])


# ------------------------------------------------------------------ geometry

def test_endings_fit_is_symmetric_and_face_to_face():
    a = [(0.0, 0.0), (10.0, 0.0)]
    b = [(10.0, 0.0), (0.0, 0.0)]
    assert endings_fit(a, b)
    assert endings_fit(b, a)
    assert not endings_fit(a, a)
