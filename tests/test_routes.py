"""Route-level smoke tests via the Flask test client."""

from werkzeug.security import generate_password_hash


def _login(client, app, user_id, name="alice"):
    """Set a session cookie that pretends ``user_id`` is logged in."""
    with client.session_transaction() as s:
        s["user_id"] = user_id
        s["user_name"] = name


def test_index_anonymous(client):
    """Anonymous visitors see the sandbox editor."""
    assert client.get("/").status_code == 200


def test_login_get(client):
    assert client.get("/user_login").status_code == 200


def test_register_get(client):
    assert client.get("/user_register").status_code == 200


def test_protected_routes_redirect_when_anonymous(client):
    for path in ("/track_open", "/library_set", "/user_info", "/user_delete"):
        r = client.get(path)
        assert r.status_code == 302, f"{path} did not redirect: {r.status_code}"


def test_authenticated_can_open_tracks(client, app, user_id):
    _login(client, app, user_id)
    assert client.get("/track_open").status_code == 200
    assert client.get("/library_set").status_code == 302  # redirects to /user_info
    assert client.get("/user_info").status_code == 200


def test_register_creates_user(client, app):
    r = client.post(
        "/user_register",
        data={"name": "carol", "password": "pw", "confirmation": "pw"},
    )
    assert r.status_code == 302
    with app.app_context():
        from duplo.repositories.users import users_read
        assert len(users_read("carol")) == 1


def test_login_with_correct_password(client, app):
    from duplo.repositories.users import users_create

    with app.app_context():
        users_create("dave", generate_password_hash("secret"))

    r = client.post("/user_login", data={"name": "dave", "password": "secret"})
    assert r.status_code == 302


def test_login_wrong_password(client, app):
    from duplo.repositories.users import users_create

    with app.app_context():
        users_create("eve", generate_password_hash("right"))

    r = client.post("/user_login", data={"name": "eve", "password": "wrong"})
    # error() renders error.html with status 200
    assert r.status_code == 200
    assert b"Invalid password" in r.data


def test_track_create_and_open_round_trip(client, app, user_id):
    _login(client, app, user_id)
    r = client.post("/track_create", data={"title": "Loop1"})
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/track_edit")
    r = client.get("/track_open")
    assert r.status_code == 200
    assert b"Loop1" in r.data


def test_register_adopts_sandbox_track(client, app):
    """Sandbox pieces created before registration are saved as a track."""
    # 1. Add a piece in the sandbox
    r = client.post(
        "/sandbox/action",
        json={"op": "add_piece", "type": "straight", "x": 100, "y": 50, "rot": 0},
    )
    assert r.json["ok"]

    # 2. Register a new account
    r = client.post(
        "/user_register",
        data={"name": "newbie", "password": "pw", "confirmation": "pw"},
    )
    assert r.status_code == 302

    # 3. The user should now have a track named "Sandbox"
    with app.app_context():
        from duplo.repositories.users import users_read
        from duplo.repositories.tracks import tracks_read

        uid = users_read("newbie")[0]["id"]
        tracks = tracks_read(uid)
        assert len(tracks) == 1
        assert tracks[0]["title"] == "Sandbox"
