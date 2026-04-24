"""Repository functions for ``pieces`` and ``connections``, plus layout helpers.

Connections are represented throughout the app as a plain list of dicts
``[{"p1":..., "e1":..., "p2":..., "e2":...}, ...]``. This keeps the data
structure JSON-serialisable and removes the pandas dependency.
"""

from ..extensions import sql
from ..services.geometry import add_piece
from ..services.track_types import zero_position


def pieces_update(track_id, pieces):
    sql("delete from pieces where track_id = :track_id", track_id=track_id)
    for (idx, piece) in enumerate(pieces):
        sql(
            "insert into pieces (track_id, idx, piece) values (:track_id, :idx, :piece)",
            track_id=track_id, idx=idx, piece=piece,
        )


def connections_update(track_id, connections):
    sql("delete from connections where track_id = :track_id", track_id=track_id)
    for c in connections:
        sql(
            "insert into connections (track_id, p1, e1, p2, e2)"
            " values (:track_id, :p1, :e1, :p2, :e2)",
            track_id=track_id,
            p1=int(c["p1"]), e1=int(c["e1"]),
            p2=int(c["p2"]), e2=int(c["e2"]),
        )


def pieces_read(track_id):
    return sql(
        "select piece from pieces where track_id = :track_id order by idx",
        track_id=track_id,
    )


def connections_read(track_id):
    return sql(
        "select p1, e1, p2, e2 from connections where track_id = :track_id",
        track_id=track_id,
    )


def pieces_read_all():
    return sql("select * from pieces")


def connections_read_all():
    return sql("select * from connections")


def layouts_parse(track_id):
    pieces = [i["piece"] for i in pieces_read(track_id=track_id)]
    connections = [
        {"p1": r["p1"], "e1": r["e1"], "p2": r["p2"], "e2": r["e2"]}
        for r in connections_read(track_id=track_id)
    ]
    return pieces, connections


def layouts_build(pieces, connections):
    pathes = []
    centerlines_per_piece = []
    all_endings = {-1: [zero_position()]}
    # Index connections by p2 for O(1) lookup of "what feeds piece idx".
    by_p2 = {c["p2"]: c for c in connections}
    for idx, piece in enumerate(pieces):
        c = by_p2[idx]
        cursor_position = all_endings[c["p1"]][c["e1"]]
        pts, endings, cls = add_piece(piece, cursor_position, c["e2"])
        pathes.append(pts)
        centerlines_per_piece.append(cls)
        all_endings[idx] = endings
    return pathes, all_endings, centerlines_per_piece


def layouts_free_endings(endings, connections):
    lst = []
    for piece_idx, ends in endings.items():
        for (ending_idx, _) in enumerate(ends):
            if any(c["p1"] == piece_idx and c["e1"] == ending_idx for c in connections):
                continue
            if any(
                c["p1"] != -1 and c["p2"] == piece_idx and c["e2"] == ending_idx
                for c in connections
            ):
                continue
            lst.append((piece_idx, ending_idx))
    # Now the interesting part - what about connections that should be there, because two endings overlap!
    to_be_removed = []
    n = len(lst)
    for i in range(n):
        for j in range(i + 1, n):
            p1, e1 = lst[i]
            p2, e2 = lst[j]
            pt1_1, pt1_2 = endings[p1][e1]
            pt2_1, pt2_2 = endings[p2][e2]
            if fitting(pt1_1, pt1_2, pt2_1, pt2_2):
                to_be_removed += [(p1, e1), (p2, e2)]

    lst = [i for i in lst if i not in to_be_removed]
    return lst


def fitting(pt1_1, pt1_2, pt2_1, pt2_2):
    res = abs(pt1_1[0] - pt2_2[0]) + abs(pt1_1[1] - pt2_2[1]) + abs(pt1_2[0] - pt2_1[0]) + abs(pt1_2[1] - pt2_1[1])
    return res < 10
