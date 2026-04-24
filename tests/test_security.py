"""Security smoke tests: CSRF on POST and rate limit on auth endpoints."""

import os

import pytest

from duplo import create_app
from duplo.extensions import db, limiter

from tests.conftest import _alembic_upgrade


@pytest.fixture
def secured_app(tmp_path, monkeypatch):
    """Build an app with CSRF + rate limiting actually enabled."""
    monkeypatch.setenv("DUPLO_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setenv("DUPLO_CSRF", "1")
    monkeypatch.setenv("DUPLO_RATELIMIT", "1")
    monkeypatch.setattr(
        "duplo.services.thumbnails._thumb_dir",
        lambda: str(tmp_path / "thumbnails"),
    )
    app = create_app()
    with app.app_context():
        _alembic_upgrade(db.engine)
        # Reset the in-memory limiter between tests so they don't bleed counts.
        limiter.reset()
        yield app


def test_post_without_csrf_token_is_rejected(secured_app):
    client = secured_app.test_client()
    resp = client.post("/user_register", data={"name": "x", "password": "y", "confirmation": "y"})
    assert resp.status_code == 400  # CSRF failure -> 400 by default


def test_login_rate_limit_kicks_in(secured_app):
    client = secured_app.test_client()
    # Limit is "10 per minute" on POST. Use bad creds so we always get an error
    # response rather than a redirect; either way it counts toward the limit.
    seen_429 = False
    for _ in range(15):
        resp = client.post(
            "/user_login",
            data={"name": "ghost", "password": "nope"},
            # CSRF must be satisfied; easiest way is to disable it just here.
            # We can't easily mint a token without first GETting the form, so
            # bypass via WTF_CSRF_ENABLED at runtime.
            headers={"X-CSRFToken": "bypass"},
        )
        if resp.status_code == 429:
            seen_429 = True
            break
    # If CSRF blocks before we ever hit the limiter we won't see 429; flip
    # the config and rerun on this same app instance.
    if not seen_429:
        secured_app.config["WTF_CSRF_ENABLED"] = False
        for _ in range(15):
            resp = client.post("/user_login", data={"name": "ghost", "password": "nope"})
            if resp.status_code == 429:
                seen_429 = True
                break
    assert seen_429, "rate limiter never returned 429"
