"""Repository functions for the ``users`` table."""

from ..extensions import sql

# --- SQLite
# CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, hash TEXT NOT NULL,
# straight INTEGER, curve INTEGER, switch INTEGER, crossing INTEGER);

# --- MySQL
# CREATE TABLE users (id int NOT NULL AUTO_INCREMENT, name TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY (id),
# straight INT, curve INT, switch INT, crossing INT);


def users_create(name, hash):
    return sql(
        "insert into users (name, hash, straight, curve, switch, crossing)"
        " values (:name, :hash, 8, 12, 2, 1)",
        name=name, hash=hash,
    )


def users_read(name):
    return sql("select id from users where name = :name", name=name)


def users_read_by_id(id):
    return sql("select id, name from users where id = :id", id=id)


def users_read_hash(name):
    return sql("select hash from users where name = :name", name=name)


def users_delete(user_id):
    sql("PRAGMA foreign_keys=ON")
    return sql("delete from users where id = :id", id=user_id)


def users_read_all():
    return sql("select * from users")


def users_library_set(user_id, straight, curve, switch, crossing):
    return sql(
        "update users set straight = :straight, curve = :curve, "
        "switch = :switch, crossing = :crossing where id = :id",
        straight=int(straight), curve=int(curve),
        switch=int(switch), crossing=int(crossing), id=user_id,
    )


def users_library_read(user_id):
    return sql(
        "select straight, curve, switch, crossing from users where id = :id",
        id=user_id,
    )
