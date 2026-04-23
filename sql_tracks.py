from helpers import sql

# --- SQLite
# CREATE TABLE tracks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT NOT NULL,
# CONSTRAINT fk_users FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE);

# --- MySQL
# CREATE TABLE tracks (id INT NOT NULL AUTO_INCREMENT, user_id INT NOT NULL, title TEXT NOT NULL, PRIMARY KEY (id),
# CONSTRAINT fk_users FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE);

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