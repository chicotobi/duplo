"""Repository smoke tests against an in-memory SQLite (pose-based pieces)."""

from duplo.repositories.layouts import (
    layouts_build,
    layouts_connections,
    layouts_free_endings,
    layouts_parse,
    pieces_read,
    pieces_update,
    piece_insert,
    piece_update_pose,
    piece_delete,
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
from duplo.services.geometry import world_endings_for_pose


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


def test_pieces_round_trip(app, track_id):
    with app.app_context():
        ids = pieces_update(track_id=track_id, pieces=[
            {"type": "straight", "x": 0.0, "y": 0.0, "rot": 0},
            {"type": "curve",    "x": 5.0, "y": 40.0, "rot": 1},
        ])
        assert len(ids) == 2 and all(i > 0 for i in ids)
        loaded = pieces_read(track_id=track_id)
        assert [p["type"] for p in loaded] == ["straight", "curve"]
        assert loaded[1]["rot"] == 1
        assert loaded[1]["x"] == 5.0


def test_piece_insert_update_delete(app, track_id):
    with app.app_context():
        pid = piece_insert(track_id, "switch", 1.0, 2.0, 3)
        assert pid > 0
        piece_update_pose(track_id, pid, 10.0, 20.0, 6)
        rows = pieces_read(track_id=track_id)
        assert rows == [{"id": pid, "type": "switch", "x": 10.0, "y": 20.0, "rot": 6}]
        piece_delete(track_id, pid)
        assert pieces_read(track_id=track_id) == []


def test_layouts_build_returns_world_geometry(app, track_id):
    with app.app_context():
        ids = pieces_update(track_id=track_id, pieces=[
            {"type": "straight", "x": 0.0, "y": 0.0, "rot": 0},
        ])
        pieces = layouts_parse(track_id)
        pathes, all_eds, cls = layouts_build(pieces)
        assert len(pathes) == 1
        assert ids[0] in all_eds
        assert len(all_eds[ids[0]]) == 2


def test_layouts_connections_detects_coincident_endings(app, track_id):
    with app.app_context():
        ids = pieces_update(track_id=track_id, pieces=[
            {"type": "straight", "x": 0.0, "y": 0.0,  "rot": 0},
            {"type": "straight", "x": 0.0, "y": 40.0, "rot": 0},
        ])
        _, all_eds, _ = layouts_build(layouts_parse(track_id))
        conns = layouts_connections(all_eds)
        assert len(conns) == 1
        a, b = conns[0]
        assert {a[0], b[0]} == set(ids)


def test_layouts_free_endings_excludes_connected(app, track_id):
    with app.app_context():
        pieces_update(track_id=track_id, pieces=[
            {"type": "straight", "x": 0.0, "y": 0.0,  "rot": 0},
            {"type": "straight", "x": 0.0, "y": 40.0, "rot": 0},
        ])
        _, all_eds, _ = layouts_build(layouts_parse(track_id))
        free = layouts_free_endings(all_eds)
        assert len(free) == 2


def test_layouts_connections_never_connects_piece_to_itself(app, track_id):
    with app.app_context():
        pieces_update(track_id=track_id, pieces=[
            {"type": "straight", "x": 0.0, "y": 0.0, "rot": 0},
        ])
        _, all_eds, _ = layouts_build(layouts_parse(track_id))
        assert layouts_connections(all_eds) == []


def test_world_endings_for_pose_matches_persisted(app, track_id):
    with app.app_context():
        pieces_update(track_id=track_id, pieces=[
            {"type": "curve", "x": 12.0, "y": 7.0, "rot": 4},
        ])
        _, all_eds, _ = layouts_build(layouts_parse(track_id))
        pid = list(all_eds.keys())[0]
        from_pose = world_endings_for_pose("curve", 12.0, 7.0, 4)
        for a, b in zip(all_eds[pid], from_pose):
            for pa, pb in zip(a, b):
                assert abs(pa[0] - pb[0]) < 1e-9
                assert abs(pa[1] - pb[1]) < 1e-9
