"""Repository functions for the ``tracks`` table."""

from ..extensions import sql


def tracks_create(user_id, title):
    return sql(
        "insert into tracks (user_id, title) values (:user_id, :title)",
        user_id=user_id, title=title,
    )


def tracks_read(user_id):
    return sql(
        "select id, title from tracks where user_id = :user_id",
        user_id=user_id,
    )


def tracks_read_title(user_id, title):
    return sql(
        "select id from tracks where user_id = :user_id and title = :title",
        user_id=user_id, title=title,
    )


def tracks_update_title(user_id, track_id, new_title):
    return sql(
        "update tracks set title = :title where user_id = :user_id and id = :id",
        title=new_title, user_id=user_id, id=track_id,
    )


def tracks_delete(user_id, track_id):
    sql("PRAGMA foreign_keys=ON")
    return sql(
        "delete from tracks where user_id = :user_id and id = :id",
        user_id=user_id, id=track_id,
    )


def tracks_read_id(id):
    return sql("select title from tracks where id = :id", id=id)


def tracks_read_all():
    return sql("select * from tracks")
