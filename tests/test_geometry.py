"""Pure-function tests for the geometry module (no Flask, no DB)."""

import math

import pytest

from duplo.services.geometry import (
    PIECE_TYPES,
    add_piece,
    affine_trafo,
    centerlines,
    endings,
    get_path_cursor,
    points,
)
from duplo.services.track_types import zero_position


def test_piece_types_have_data():
    for t in PIECE_TYPES:
        assert t in points and len(points[t]) > 0
        assert t in endings and len(endings[t]) > 0
        assert t in centerlines and len(centerlines[t]) > 0


def test_endings_count_matches_piece_topology():
    assert len(endings["straight"]) == 2
    assert len(endings["curve"]) == 2
    assert len(endings["switch"]) == 3
    assert len(endings["crossing"]) == 4


def test_affine_trafo_identity():
    src = [(0.0, 0.0), (1.0, 0.0)]
    trafo = affine_trafo(src, src)
    for p in [(0.0, 0.0), (1.0, 0.0), (5.0, -3.0)]:
        out = trafo(p)
        assert math.isclose(out[0], p[0], abs_tol=1e-9)
        assert math.isclose(out[1], p[1], abs_tol=1e-9)


def test_affine_trafo_translation():
    src = [(0.0, 0.0), (1.0, 0.0)]
    dst = [(10.0, 5.0), (11.0, 5.0)]
    trafo = affine_trafo(src, dst)
    out = trafo((0.0, 0.0))
    assert math.isclose(out[0], 10.0, abs_tol=1e-9)
    assert math.isclose(out[1], 5.0, abs_tol=1e-9)


@pytest.mark.parametrize("piece_type", PIECE_TYPES)
def test_add_piece_returns_well_formed(piece_type):
    pts, e_out, cls = add_piece(piece_type, zero_position(), 0)
    assert len(pts) == len(points[piece_type])
    assert len(e_out) == len(endings[piece_type])
    assert len(cls) == len(centerlines[piece_type])
    for p in pts:
        assert "x" in p and "y" in p


def test_get_path_cursor_returns_three_points():
    cursor = [(0.0, 0.0), (10.0, 0.0)]
    pts = get_path_cursor(cursor)
    assert len(pts) == 3
    assert pts[0]["x"] == 0.0 and pts[1]["x"] == 10.0
