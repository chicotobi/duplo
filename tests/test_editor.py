"""Tests for the pose-based LayoutEditor state machine."""

import pytest

from duplo.repositories.layouts import layouts_parse
from duplo.services.editor import LayoutEditor


USER_LIB = {"straight": 99, "curve": 99, "switch": 99, "crossing": 99}


def test_load_empty_track(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        assert editor.pieces == []
        assert editor.selection is None
        assert not editor.is_closed()


def test_add_piece_appends_and_selects(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        pid = editor.add_piece("straight", 10.0, 20.0, 1)
        assert len(editor.pieces) == 1
        assert editor.pieces[0]["type"] == "straight"
        assert editor.pieces[0]["x"] == 10.0
        assert editor.pieces[0]["rot"] == 1
        assert editor.selection == {"piece_id": pid, "ending_idx": None}


def test_add_unknown_type_raises(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        with pytest.raises(ValueError):
            editor.add_piece("rocket", 0, 0, 0)


def test_move_and_rotate_piece(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        pid = editor.add_piece("curve", 0, 0, 0)
        editor.move_piece(pid, 100.0, -50.0, 5)
        assert editor.pieces[0]["x"] == 100.0
        assert editor.pieces[0]["y"] == -50.0
        assert editor.pieces[0]["rot"] == 5
        editor.rotate_piece(pid, delta_steps=2)
        assert editor.pieces[0]["rot"] == 7
        editor.rotate_piece(pid, delta_steps=-9)
        assert editor.pieces[0]["rot"] == 10  # (7 - 9) mod 12 == 10


def test_delete_arbitrary_piece(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        a = editor.add_piece("straight", 0, 0, 0)
        b = editor.add_piece("straight", 100, 0, 0)
        c = editor.add_piece("straight", 200, 0, 0)
        editor.delete_piece(b)
        assert [p["id"] for p in editor.pieces] == [a, c]


def test_delete_clears_selection_when_target(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        pid = editor.add_piece("straight", 0, 0, 0)
        editor.select(pid, 0)
        editor.delete_piece(pid)
        assert editor.selection is None


def test_select_validates_ending_idx(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        pid = editor.add_piece("straight", 0, 0, 0)
        editor.select(pid, 1)
        assert editor.selection == {"piece_id": pid, "ending_idx": 1}
        with pytest.raises(ValueError):
            editor.select(pid, 5)


def test_commit_move_snaps_when_close(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        a = editor.add_piece("straight", 0.0, 0.0, 0)
        b = editor.add_piece("straight", 2.0, 41.5, 0)
        result = editor.commit_move(b, 1.0, 41.0, 0, anchor_ending_idx=0)
        assert result["snapped"] is True
        assert result["target"]["piece_id"] == a
        b_piece = next(p for p in editor.pieces if p["id"] == b)
        assert b_piece["x"] == 0.0
        assert b_piece["y"] == 40.0


def test_commit_move_no_snap_when_far(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        editor.add_piece("straight", 0.0, 0.0, 0)
        b = editor.add_piece("straight", 500.0, 500.0, 0)
        result = editor.commit_move(b, 600.0, 600.0, 3)
        assert result["snapped"] is False
        b_piece = next(p for p in editor.pieces if p["id"] == b)
        assert b_piece["x"] == 600.0
        assert b_piece["rot"] == 3


def test_save_persists_and_remaps_ids(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        provisional = editor.add_piece("straight", 0, 0, 0)
        assert provisional < 0
        editor.save()
        assert all(p["id"] > 0 for p in editor.pieces)
        if editor.selection:
            assert editor.selection["piece_id"] > 0
        loaded = layouts_parse(track_id)
        assert len(loaded) == 1
        assert loaded[0]["type"] == "straight"


def test_session_round_trip(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        editor.add_piece("straight", 0, 0, 0)
        editor.add_piece("curve", 5, 40, 1)
        snap = editor.to_session()
        restored = LayoutEditor.from_session(
            track_id, snap["pieces"], snap["selection"], snap["next_provisional_id"],
        )
        assert restored.pieces == editor.pieces
        assert restored.selection == editor.selection


def test_view_model_shape(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        pid = editor.add_piece("straight", 0, 0, 0)
        vm = editor.view_model(USER_LIB)
        assert set(vm.keys()) >= {"pieces", "connections", "selection",
                                  "is_closed", "counter", "snap_tolerance"}
        assert vm["counter"]["straight"] == 1
        assert vm["pieces"][0]["id"] == pid
        assert vm["pieces"][0]["type"] == "straight"
        assert "endings" in vm["pieces"][0]
        assert all("free" in e for e in vm["pieces"][0]["endings"])
        assert vm["connections"] == []
        assert vm["selection"] == {"piece_id": pid, "ending_idx": None}


def test_view_model_marks_connected_endings(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        editor.add_piece("straight", 0.0, 0.0,  0)
        editor.add_piece("straight", 0.0, 40.0, 0)
        vm = editor.view_model(USER_LIB)
        assert len(vm["connections"]) == 1
        for p in vm["pieces"]:
            free = sum(1 for e in p["endings"] if e["free"])
            assert free == 1
        assert vm["is_closed"] is False
