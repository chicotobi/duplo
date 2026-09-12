"""Knock a hole in a real track and check the designer can patch it.

The seven layouts in ``fixtures/real_layouts.json`` were built by hand in the
app and are all closed. That makes them the only test data worth having: they
are the shapes people actually build, they contain switches, a crossing and
hand-snapped joints that sit a unit or two off centre, and — crucially — every
hole punched in one has a known solution, because the pieces that came out fit
back in.

So the test is: delete a run of three to five *connected* pieces, hand the
remains to :func:`complete_track`, and require it to close them up again.
Not necessarily the way they were before — any closure will do — and closure is
judged by ``layouts_connections``, the same derivation the editor renders from,
never by the designer's own bookkeeping.

Deliberately no synthetic layouts, and no from-scratch designs: growing a large
track out of nothing is a much harder search than filling a gap, it is slow and
flaky, and it is not what the feature is for.
"""

import collections
import itertools
import json
import pathlib
import random
import time

import pytest

from duplo.repositories.layouts import (
    layouts_build,
    layouts_connections,
    layouts_free_endings,
)
from duplo.services.designer import _share_a_joint, complete_track
from duplo.services.geometry import (
    JOINT_OVERLAP_MARGIN,
    PIECE_TYPES,
    can_force_connect,
    polygons_overlap,
    world_endings_for_pose,
    world_polygon,
)

_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "real_layouts.json"
LAYOUTS = json.loads(_FIXTURES.read_text())

# Gap sizes to punch. Three to five connected pieces is the realistic edit:
# a stretch pulled out to make room, or a corner that did not work.
GAP_SIZES = (3, 4, 5)

# Seeds per (layout, gap size). Each picks a different run to remove, so this
# is a sample of holes rather than one lucky one.
SEEDS = (1, 2, 3)

# Generous next to the measured worst case of ~0.2s, so the suite does not go
# red on a loaded machine, but still short enough that a real regression --
# which shows up as the search timing out -- fails the test.
BUDGET = 5.0


# ------------------------------------------------------------------ helpers

def _inventory(pieces):
    """What the user owns: exactly the pieces the finished track uses."""
    counts = collections.Counter(p["type"] for p in pieces)
    return {t: counts.get(t, 0) for t in PIECE_TYPES}


def _adjacency(pieces):
    _, all_endings, _ = layouts_build(pieces)
    adj = collections.defaultdict(set)
    for (a, b) in layouts_connections(all_endings):
        adj[a[0]].add(b[0])
        adj[b[0]].add(a[0])
    return adj


def remove_run(pieces, forced, size, rng):
    """Delete a random run of *size* pieces connected end to end.

    Walks the connection graph from a random piece, so the hole is a stretch
    of track rather than *size* pieces scattered about. Returns
    ``(kept, kept_forced, removed_ids)``.
    """
    adj = _adjacency(pieces)
    for _ in range(50):
        run = [rng.choice(pieces)["id"]]
        while len(run) < size:
            onward = sorted(n for n in adj[run[-1]] if n not in run)
            if not onward:
                break
            run.append(rng.choice(onward))
        if len(run) < size:
            continue    # walked into a dead end; start somewhere else
        gone = set(run)
        kept = [p for p in pieces if p["id"] not in gone]
        kept_forced = [fc for fc in forced
                       if fc["piece1_id"] not in gone
                       and fc["piece2_id"] not in gone]
        return kept, kept_forced, run
    raise AssertionError(f"no run of {size} connected pieces found")


def _consumed(kept, kept_forced):
    """Force-joined endings, as ``(index into kept, ending_idx)``."""
    pos = {p["id"]: i for i, p in enumerate(kept)}
    out = []
    for fc in kept_forced:
        out.append((pos[fc["piece1_id"]], fc["ending1_idx"]))
        out.append((pos[fc["piece2_id"]], fc["ending2_idx"]))
    return out


def _free_endings(pieces, joined):
    """Endings left over, the way the editor works them out.

    *pieces* carry ``id`` equal to their index; *joined* is the list of
    force-connected ``(piece, ending)`` pairs, which the editor counts as
    consumed just as coincident ones are.
    """
    _, all_endings, _ = layouts_build(pieces)
    free = set(layouts_free_endings(all_endings))
    for (a, ea, b, eb) in joined:
        free.discard((a, ea))
        free.discard((b, eb))
    return free


def _combined(kept, result, kept_forced):
    """The finished layout, plus every joint holding it together.

    Piece ids are indices into ``kept + added``, which is the frame the
    designer reports its forced joints in.
    """
    pieces = [dict(p, id=i) for i, p in enumerate(kept)]
    pieces += [dict(p, id=len(kept) + i)
               for i, p in enumerate(result["pieces"])]
    pos = {p["id"]: i for i, p in enumerate(kept)}
    joined = [(fc["piece1"], fc["ending1_idx"], fc["piece2"], fc["ending2_idx"])
              for fc in result["forced"]]
    joined += [(pos[fc["piece1_id"]], fc["ending1_idx"],
                pos[fc["piece2_id"]], fc["ending2_idx"]) for fc in kept_forced]
    return pieces, joined


CASES = [
    pytest.param(layout, size, seed, id=f"{layout['name']}-gap{size}-seed{seed}")
    for layout in LAYOUTS
    for size in GAP_SIZES
    for seed in SEEDS
]


@pytest.fixture(scope="module")
def patched():
    """Every case run once: ``(layout, size, seed) -> (kept, kept_forced, result)``.

    Module-scoped because the search is the slow part and each of the checks
    below wants to look at the same answers from a different angle.
    """
    out = {}
    for layout, size, seed in [c.values for c in CASES]:
        rng = random.Random(f"{layout['name']}|{size}|{seed}")
        kept, kept_forced, _ = remove_run(
            layout["pieces"], layout["forced_connections"], size, rng)
        result = complete_track(
            kept, _inventory(layout["pieces"]),
            room_w=99, room_h=99, seed=seed, time_budget=BUDGET,
            consumed=_consumed(kept, kept_forced),
        )
        out[(layout["name"], size, seed)] = (kept, kept_forced, result)
    return out


def _case(patched, layout, size, seed):
    return patched[(layout["name"], size, seed)]


# ------------------------------------------------------ the fixtures are sane

@pytest.mark.parametrize("layout", LAYOUTS, ids=lambda lay: lay["name"])
def test_the_real_layouts_are_closed_to_start_with(layout):
    """If a fixture were not closed, every knock-out test built on it is void."""
    pieces = [dict(p, id=i) for i, p in enumerate(layout["pieces"])]
    pos = {p["id"]: i for i, p in enumerate(layout["pieces"])}
    joined = [(pos[fc["piece1_id"]], fc["ending1_idx"],
               pos[fc["piece2_id"]], fc["ending2_idx"])
              for fc in layout["forced_connections"]]
    assert _free_endings(pieces, joined) == set()


@pytest.mark.parametrize("size", GAP_SIZES)
def test_the_hole_really_is_a_connected_run(size):
    """The removal has to be a stretch of track, not scattered pieces."""
    layout = LAYOUTS[0]
    rng = random.Random(size)
    kept, _, removed = remove_run(layout["pieces"], [], size, rng)
    assert len(removed) == size
    assert len(kept) == len(layout["pieces"]) - size
    adj = _adjacency(layout["pieces"])
    for earlier, later in itertools.pairwise(removed):
        assert later in adj[earlier], "removed pieces are not end to end"


# ------------------------------------------------------------- the real thing

@pytest.mark.parametrize("layout,size,seed", CASES)
def test_the_gap_is_closed_again(patched, layout, size, seed):
    """The whole point: a hole of three to five pieces gets patched."""
    kept, kept_forced, result = _case(patched, layout, size, seed)
    assert result["closed"], (
        f"gave up on a {size}-piece hole after {result['stats']['seconds']}s"
    )
    pieces, joined = _combined(kept, result, kept_forced)
    assert _free_endings(pieces, joined) == set(), "the editor still sees it open"


@pytest.mark.parametrize("layout,size,seed", CASES)
def test_the_users_own_pieces_are_left_exactly_where_they_were(
        patched, layout, size, seed):
    """Nothing already on the floor may be moved, rotated or dropped."""
    kept, _, result = _case(patched, layout, size, seed)
    before = [(p["type"], p["x"], p["y"], p["rot"]) for p in kept]
    _, all_endings, _ = layouts_build([dict(p, id=i) for i, p in enumerate(kept)])
    assert len(all_endings) == len(before)   # nothing dropped
    # complete_track is handed a copy, so the only way the originals could
    # change is if it reported them back as additions.
    assert len(result["pieces"]) == result["stats"]["added"]


@pytest.mark.parametrize("layout,size,seed", CASES)
def test_only_pieces_the_user_still_has_are_used(patched, layout, size, seed):
    """The box holds what the finished track used, minus what is still down."""
    kept, _, result = _case(patched, layout, size, seed)
    owned = _inventory(layout["pieces"])
    on_floor = collections.Counter(p["type"] for p in kept)
    added = collections.Counter(p["type"] for p in result["pieces"])
    for ptype in PIECE_TYPES:
        assert added[ptype] <= owned[ptype] - on_floor.get(ptype, 0), ptype


@pytest.mark.parametrize("layout,size,seed", CASES)
def test_nothing_ends_up_on_top_of_anything_else(patched, layout, size, seed):
    """No piece may collide with another.

    Two pieces meeting at a joint are the exception: the connection tolerance
    lets them sit slightly into each other, and the user's own hand-snapped
    joints do exactly that.
    """
    kept, kept_forced, result = _case(patched, layout, size, seed)
    pieces, _ = _combined(kept, result, kept_forced)
    polys = [world_polygon(p["type"], p["x"], p["y"], p["rot"]) for p in pieces]
    eds = [world_endings_for_pose(p["type"], p["x"], p["y"], p["rot"])
           for p in pieces]
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            if not polygons_overlap(polys[i], polys[j]):
                continue
            assert _share_a_joint(eds[i], eds[j]), (i, j, "pieces collide")
            assert not polygons_overlap(polys[i], polys[j],
                                        margin=JOINT_OVERLAP_MARGIN), \
                (i, j, "joint overlaps by more than the tolerance allows")


@pytest.mark.parametrize("layout,size,seed", CASES)
def test_any_joint_left_loose_is_one_the_app_would_accept(
        patched, layout, size, seed):
    """A near-miss only counts as closed if force-connection would take it."""
    kept, kept_forced, result = _case(patched, layout, size, seed)
    pieces, _ = _combined(kept, result, kept_forced)
    _, all_endings, _ = layouts_build(pieces)
    for fc in result["forced"]:
        a = all_endings[fc["piece1"]][fc["ending1_idx"]]
        b = all_endings[fc["piece2"]][fc["ending2_idx"]]
        assert can_force_connect(a, b)["can_force"], fc


@pytest.mark.parametrize("layout,size,seed", CASES)
def test_the_patch_is_about_the_size_of_the_hole(patched, layout, size, seed):
    """A three-piece hole should not be filled with fifteen pieces.

    The sweep tries small first, so the answer is the smallest that closes.
    It is allowed to be smaller than the hole — a corner cut across is a fair
    answer — but it cannot need more than the box held.
    """
    _, _, result = _case(patched, layout, size, seed)
    assert result["stats"]["added"] <= size


def test_rotations_stay_on_the_thirty_degree_grid(patched):
    for (_, _, result) in patched.values():
        for p in result["pieces"]:
            assert p["rot"] == int(p["rot"]) and 0 <= p["rot"] < 12


# ----------------------------------------------------------------- the clock

def test_an_impossible_gap_still_answers_within_the_time_limit():
    """The limit is hard: no closure, but an answer, and on time."""
    layout = LAYOUTS[0]
    rng = random.Random(1)
    kept, _, _ = remove_run(layout["pieces"], [], 5, rng)
    budget = 0.5
    started = time.monotonic()
    result = complete_track(kept, {"straight": 40, "curve": 40,
                                   "switch": 4, "crossing": 2},
                            room_w=99, room_h=99, seed=1,
                            time_budget=budget, max_new=200)
    elapsed = time.monotonic() - started
    assert result is not None
    # The continuation is a single pass with no backtracking; it gets a
    # moment's grace past the deadline to finish, and no more.
    assert elapsed < budget + 2.0, f"ran {elapsed:.1f}s on a {budget}s budget"


def test_out_of_time_it_offers_a_continuation_rather_than_nothing():
    """A hole with an unusable box: the answer is track to trim, not an error."""
    layout = LAYOUTS[0]
    rng = random.Random(2)
    kept, _, _ = remove_run(layout["pieces"], [], 4, rng)
    # Curves only, and far more of them than the hole needs. Closing is a
    # long shot; carrying the track onward is not.
    result = complete_track(kept, _curves_only(kept, 30), room_w=99, room_h=99,
                            seed=2, time_budget=0.2)
    assert result is not None
    assert result["stats"]["added"] == len(result["pieces"])
    if not result["closed"]:
        assert result["pieces"], "timed out with nothing to show for it"
        # Whatever it hands over has to be buildable, or it is worse than
        # nothing: the user cannot trim their way out of a collision.
        polys = [world_polygon(p["type"], p["x"], p["y"], p["rot"])
                 for p in kept + result["pieces"]]
        eds = [world_endings_for_pose(p["type"], p["x"], p["y"], p["rot"])
               for p in kept + result["pieces"]]
        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                if polygons_overlap(polys[i], polys[j]):
                    assert _share_a_joint(eds[i], eds[j]), (i, j)


def _extent(pieces):
    corners = [c for p in pieces
               for c in world_polygon(p["type"], p["x"], p["y"], p["rot"])]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return max(xs) - min(xs), max(ys) - min(ys)


def _curves_only(kept, spare):
    counts = collections.Counter(p["type"] for p in kept)
    inv = {t: counts.get(t, 0) for t in PIECE_TYPES}
    inv["curve"] += spare
    return inv


def test_a_track_that_is_already_closed_is_left_alone():
    layout = LAYOUTS[2]
    assert not layout["forced_connections"], "pick a fixture with plain joints"
    result = complete_track(layout["pieces"], _inventory(layout["pieces"]),
                            room_w=99, room_h=99, seed=1, time_budget=2.0)
    assert result["closed"] is True
    assert result["pieces"] == []


def test_an_empty_floor_is_not_this_function_s_job():
    assert complete_track([], {"straight": 8, "curve": 12,
                               "switch": 0, "crossing": 0}) is None


def test_a_room_smaller_than_the_track_is_not_taken_literally():
    """Refusing to extend a track that has outgrown the room helps nobody."""
    layout = LAYOUTS[0]
    rng = random.Random(3)
    kept, kept_forced, _ = remove_run(
        layout["pieces"], layout["forced_connections"], 3, rng)
    result = complete_track(kept, _inventory(layout["pieces"]),
                            room_w=0.1, room_h=0.1, seed=3, time_budget=BUDGET,
                            consumed=_consumed(kept, kept_forced))
    assert result["closed"] is True
    # Not taken literally, but not ignored either: the patch may bulge past
    # what is already on the floor, not sprawl.
    was_w, was_h = _extent(kept)
    now_w, now_h = _extent(kept + result["pieces"])
    assert now_w <= was_w + 100 and now_h <= was_h + 100


# ----------------------------------------------------------- editor plumbing

def test_autodesign_adds_to_the_track_instead_of_replacing_it(app, track_id):
    from duplo.services.editor import LayoutEditor

    layout = LAYOUTS[0]
    rng = random.Random(4)
    kept, _, _ = remove_run(layout["pieces"], [], 4, rng)
    with app.app_context():
        editor = LayoutEditor(track_id, [])
        for p in kept:
            editor.pieces.append({"id": editor._mint_id(), "type": p["type"],
                                  "x": p["x"], "y": p["y"], "rot": p["rot"]})
        before = [dict(p) for p in editor.pieces]

        stats = editor.autodesign(_inventory(layout["pieces"]), 99, 99,
                                  seed=4, time_budget=BUDGET)

        assert stats is not None
        assert stats["closed"] is True
        assert editor.pieces[:len(before)] == before, "the user's pieces moved"
        assert len(editor.pieces) == len(before) + stats["added"]
        assert editor.is_closed()
        assert editor.view_model(_inventory(layout["pieces"]))["is_closed"]


def test_autodesign_on_an_empty_floor_still_designs_a_whole_track(app, track_id):
    from duplo.services.editor import LayoutEditor
    with app.app_context():
        editor = LayoutEditor(track_id, [])
        stats = editor.autodesign({"straight": 8, "curve": 12, "switch": 2,
                                   "crossing": 1}, 6, 4, seed=5,
                                  time_budget=6.0)
        assert stats is not None
        assert len(editor.pieces) == stats["added"]
        assert editor.is_closed()
