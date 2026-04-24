"""Pytest fixtures shared across the test suite."""

import os

# Make sure tests never accidentally hit a real MySQL or production sqlite file.
os.environ.setdefault("DUPLO_DATABASE_URI", "sqlite:///:memory:")
os.environ.setdefault("DUPLO_SECRET_KEY", "test-secret")
os.environ.setdefault("DUPLO_DEBUG", "0")
os.environ.setdefault("DUPLO_CSRF", "0")
os.environ.setdefault("DUPLO_RATELIMIT", "0")

import pytest
from alembic import command
from alembic.config import Config

from duplo import create_app
from duplo.extensions import db


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ALEMBIC_INI = os.path.join(_PROJECT_ROOT, "alembic.ini")


def _alembic_upgrade(engine):
    cfg = Config(_ALEMBIC_INI)
    cfg.set_main_option("script_location", os.path.join(_PROJECT_ROOT, "alembic"))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        # env.py uses connection from cfg.attributes when present
        command.upgrade(cfg, "head")


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Fresh in-memory SQLite app for each test."""
    monkeypatch.setenv("DUPLO_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(
        "duplo.services.thumbnails._thumb_dir",
        lambda: str(tmp_path / "thumbnails"),
    )
    app = create_app()
    with app.app_context():
        _alembic_upgrade(db.engine)
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user_id(app):
    """Create one user and return its id."""
    from duplo.repositories.users import users_create, users_read
    with app.app_context():
        users_create("alice", "hash-not-checked")
        return users_read("alice")[0]["id"]


@pytest.fixture
def track_id(app, user_id):
    """Create one empty track for the fixture user and return its id."""
    from duplo.repositories.tracks import tracks_create, tracks_read_title
    with app.app_context():
        tracks_create(user_id, "TestTrack")
        return tracks_read_title(user_id, "TestTrack")[0]["id"]
