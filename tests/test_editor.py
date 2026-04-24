"""Tests for the LayoutEditor state machine."""

from duplo.repositories.layouts import layouts_parse
from duplo.services.editor import LayoutEditor


def test_load_empty_track(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        assert editor.pieces == []
        assert editor.connections == []
        assert editor.cursor_idx == 0
        assert not editor.is_closed()


def test_add_piece_grows_pieces_and_moves_cursor(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        editor.apply_action("straight")
        assert editor.pieces == ["straight"]
        assert len(editor.connections) == 1
        assert editor.cursor_idx is not None


def test_delete_undoes_last_add(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        editor.apply_action("straight")
        editor.apply_action("straight")
        assert len(editor.pieces) == 2
        editor.apply_action("delete")
        assert editor.pieces == ["straight"]
        assert len(editor.connections) == 1


def test_delete_on_empty_is_noop(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        editor.apply_action("delete")
        assert editor.pieces == []


def test_save_persists_to_db(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        editor.apply_action("straight")
        editor.apply_action("straight")
        editor.apply_action("save")

        loaded_pieces, loaded_conns = layouts_parse(track_id)
        assert loaded_pieces == ["straight", "straight"]
        assert len(loaded_conns) == 2


def test_session_round_trip_preserves_state(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        editor.apply_action("straight")
        editor.apply_action("left")  # curve
        snapshot = editor.to_session()

        restored = LayoutEditor.from_session(
            track_id,
            snapshot["pieces"],
            snapshot["connections"],
            snapshot["cursor_idx"],
        )
        assert restored.pieces == editor.pieces
        assert restored.connections == editor.connections
        assert restored.cursor_idx == editor.cursor_idx


def test_view_model_shape(app, track_id):
    with app.app_context():
        editor = LayoutEditor.load_from_db(track_id)
        editor.apply_action("straight")
        user_lib = {"straight": 99, "curve": 99, "switch": 99, "crossing": 99}
        vm = editor.view_model(user_lib)
        assert set(vm.keys()) == {"pathes", "counter", "is_closed", "ghosts"}
        assert vm["counter"]["straight"] == 1
        # Open track => ghosts populated for all 5 actions
        assert set(vm["ghosts"].keys()) == {"straight", "left", "right", "switch", "crossing"}
