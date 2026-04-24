"""Repository smoke tests against an in-memory SQLite."""

from duplo.repositories.layouts import (
    connections_read,
    connections_update,
    layouts_parse,
    pieces_read,
    pieces_update,
)
from duplo.repositories.tracks import (
    tracks_create,
    tracks_read,
    tracks_read_title,
    tracks_update_title,
)
from duplo.repositories.users import (
    users_create,
    users_library_read,
    users_library_set,
    users_read,
)


def test_users_create_and_read(app):
    with app.app_context():
        users_create("bob", "hash")
        rows = users_read("bob")
        assert len(rows) == 1
        assert rows[0]["id"] > 0


def test_users_library_defaults_and_update(app, user_id):
    with app.app_context():
        lib = users_library_read(user_id)[0]
        assert lib == {"straight": 99, "curve": 99, "switch": 99, "crossing": 99}
        users_library_set(user_id, 5, 7, 1, 2)
        lib = users_library_read(user_id)[0]
        assert lib == {"straight": 5, "curve": 7, "switch": 1, "crossing": 2}


def test_tracks_crud(app, user_id):
    with app.app_context():
        tracks_create(user_id, "Loop")
        tid = tracks_read_title(user_id, "Loop")[0]["id"]
        assert tid > 0
        assert any(t["title"] == "Loop" for t in tracks_read(user_id))
        tracks_update_title(user_id, tid, "Loop2")
        assert tracks_read_title(user_id, "Loop2")[0]["id"] == tid


def test_pieces_and_connections_round_trip(app, track_id):
    with app.app_context():
        pieces_update(track_id=track_id, pieces=["straight", "curve", "curve"])
        conns = [
            {"p1": -1, "e1": 0, "p2": 0, "e2": 0},
            {"p1": 0, "e1": 1, "p2": 1, "e2": 0},
            {"p1": 1, "e1": 1, "p2": 2, "e2": 0},
        ]
        connections_update(track_id=track_id, connections=conns)

        loaded_pieces, loaded_conns = layouts_parse(track_id)
        assert loaded_pieces == ["straight", "curve", "curve"]
        assert len(loaded_conns) == 3
        assert set(loaded_conns[0].keys()) == {"p1", "e1", "p2", "e2"}

        assert [p["piece"] for p in pieces_read(track_id=track_id)] == [
            "straight", "curve", "curve",
        ]
        assert len(connections_read(track_id=track_id)) == 3
