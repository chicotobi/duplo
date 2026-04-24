"""Pure-function tests for the geometry module (no Flask, no DB)."""

import math

import pytest

from duplo.services.geometry import (
    PIECE_TYPES,
    SNAP_TOLERANCE,
    centerlines,
    ending_count,
    endings,
    points,
    snap_pose,
    transform_for_pose,
    world_endings_for_pose,
)


def test_piece_types_have_data():
    for t in PIECE_TYPES:
        assert t in points and len(points[t]) > 0
        assert t in endings and len(endings[t]) > 0
        assert t in centerlines and len(centerlines[t]) > 0


def test_endings_count_matches_piece_topology():
    assert ending_count == {"straight": 2, "curve": 2, "switch": 3, "crossing": 4}


@pytest.mark.parametrize("piece_type", PIECE_TYPES)
def test_transform_for_pose_well_formed(piece_type):
    pts, eds, cls = transform_for_pose(piece_type, 0.0, 0.0, 0)
    assert len(pts) == len(points[piece_type])
    assert len(eds) == len(endings[piece_type])
    assert len(cls) == len(centerlines[piece_type])
    for p in pts:
        assert "x" in p and "y" in p


def test_transform_translation_only():
    pts, _, _ = transform_for_pose("straight", 100.0, -50.0, 0)
    local = points["straight"]
    for p, l in zip(pts, local):
        assert math.isclose(p["x"], l[0] + 100.0, abs_tol=1e-9)
        assert math.isclose(p["y"], l[1] - 50.0, abs_tol=1e-9)


def test_transform_rotation_quantised():
    pts0, _, _ = transform_for_pose("straight", 0, 0, 0)
    pts12, _, _ = transform_for_pose("straight", 0, 0, 12)
    for a, b in zip(pts0, pts12):
        assert math.isclose(a["x"], b["x"], abs_tol=1e-9)
        assert math.isclose(a["y"], b["y"], abs_tol=1e-9)


def test_world_endings_match_transform():
    _, eds_full, _ = transform_for_pose("curve", 5.0, 6.0, 3)
    eds_only = world_endings_for_pose("curve", 5.0, 6.0, 3)
    assert len(eds_full) == len(eds_only)
    for ef, eo in zip(eds_full, eds_only):
        for pf, po in zip(ef, eo):
            assert math.isclose(pf[0], po[0], abs_tol=1e-9)
            assert math.isclose(pf[1], po[1], abs_tol=1e-9)


def test_snap_pose_returns_none_when_far():
    target = {"piece_id": 1, "ending_idx": 0, "pair": [[1000.0, 1000.0], [1010.0, 1000.0]]}
    res = snap_pose("straight", 0, (0.0, 0.0, 0), [target])
    assert res is None


def test_snap_pose_aligns_to_close_target():
    eds = world_endings_for_pose("straight", 50.0, 0.0, 0)
    target_pair = [list(eds[1][0]), list(eds[1][1])]
    target = {"piece_id": 7, "ending_idx": 1, "pair": target_pair}
    res = snap_pose("straight", 0, (52.0, 41.0, 0), [target], tolerance=SNAP_TOLERANCE)
    assert res is not None
    assert res["target"]["piece_id"] == 7
    sp = res["pose"]
    snapped_pair = world_endings_for_pose("straight", sp[0], sp[1], sp[2])[0]
    assert math.isclose(snapped_pair[0][0], target_pair[1][0], abs_tol=1e-6)
    assert math.isclose(snapped_pair[0][1], target_pair[1][1], abs_tol=1e-6)
    assert math.isclose(snapped_pair[1][0], target_pair[0][0], abs_tol=1e-6)
    assert math.isclose(snapped_pair[1][1], target_pair[0][1], abs_tol=1e-6)


def test_snap_pose_picks_closest_target():
    eds_close = world_endings_for_pose("straight", 50.0, 0.0, 0)[1]
    eds_far = world_endings_for_pose("straight", 53.0, 0.0, 0)[1]
    targets = [
        {"piece_id": 1, "ending_idx": 1, "pair": [list(eds_far[0]), list(eds_far[1])]},
        {"piece_id": 2, "ending_idx": 1, "pair": [list(eds_close[0]), list(eds_close[1])]},
    ]
    res = snap_pose("straight", 0, (51.0, 41.0, 0), targets, tolerance=SNAP_TOLERANCE)
    assert res is not None
    assert res["target"]["piece_id"] == 2
