"""Tests for editor_storage and the editor_states table (pose-based)."""

import json

import pytest

from duplo import create_app
from duplo.extensions import db
from duplo.repositories.editor_states import editor_state_read
from duplo.services import editor_storage
from duplo.services.editor import LayoutEditor

from tests.conftest import _alembic_upgrade


@pytest.fixture(params=[False, True], ids=["session-backend", "db-backend"])
def app(tmp_path, monkeypatch, request):
    monkeypatch.setenv("DUPLO_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setenv("DUPLO_DB_EDITOR_STATE", "1" if request.param else "0")
    monkeypatch.setattr(
        "duplo.services.thumbnails._thumb_dir",
        lambda: str(tmp_path / "thumbnails"),
    )
    app = create_app()
    with app.app_context():
        _alembic_upgrade(db.engine)
        yield app


@pytest.fixture
def user_id(app):
    from duplo.repositories.users import users_create, users_read
    with app.app_context():
        users_create("alice", "h")
        return users_read("alice")[0]["id"]


@pytest.fixture
def track_id(app, user_id):
    from duplo.repositories.tracks import tracks_create, tracks_read_title
    with app.app_context():
        tracks_create(user_id, "T1")
        return tracks_read_title(user_id, "T1")[0]["id"]


def test_save_then_load_round_trip(app, user_id, track_id):
    with app.test_request_context():
        editor = LayoutEditor.load_from_db(track_id)
        pid_a = editor.add_piece("straight", 1.0, 2.0, 3)
        pid_b = editor.add_piece("curve", 4.0, 5.0, 6)
        editor_storage.save(user_id, editor)

        assert editor_storage.has_state(user_id, track_id)
        restored = editor_storage.load(user_id, track_id)
        assert [p["type"] for p in restored.pieces] == ["straight", "curve"]
        assert restored.pieces[0]["id"] == pid_a
        assert restored.pieces[1]["id"] == pid_b
        assert restored.selection == editor.selection


def test_clear_removes_state(app, user_id, track_id):
    with app.test_request_context():
        editor = LayoutEditor.load_from_db(track_id)
        editor.add_piece("straight", 0, 0, 0)
        editor_storage.save(user_id, editor)
        editor_storage.clear(user_id, track_id)
        assert not editor_storage.has_state(user_id, track_id)


def test_db_backend_writes_row(app, user_id, track_id):
    if not app.config["DUPLO_DB_EDITOR_STATE"]:
        pytest.skip("session backend doesn't touch the DB")
    with app.test_request_context():
        editor = LayoutEditor.load_from_db(track_id)
        editor.add_piece("straight", 0, 0, 0)
        editor_storage.save(user_id, editor)

        row = editor_state_read(user_id, track_id)
        assert row is not None
        loaded = json.loads(row["pieces_json"])
        assert len(loaded) == 1 and loaded[0]["type"] == "straight"


def test_track_delete_clears_db_state(app, user_id, track_id):
    if not app.config["DUPLO_DB_EDITOR_STATE"]:
        pytest.skip("session-only backend has nothing to assert against")
    from duplo.repositories.editor_states import editor_state_delete
    with app.test_request_context():
        editor = LayoutEditor.load_from_db(track_id)
        editor.add_piece("straight", 0, 0, 0)
        editor_storage.save(user_id, editor)
        editor_state_delete(user_id, track_id)
        assert editor_state_read(user_id, track_id) is None
