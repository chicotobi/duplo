from helpers import sql

# create table tracks (id integer primary key autoincrement, user_id integer not null, title text not null);
# create table tracks (id int NOT NULL AUTO_INCREMENT, user_id int not null, title text not null, primary key (id));

def tracks_create(user_id, title):
    cmd = f"insert into tracks (user_id, title) values ('{user_id}','{title}')"
    return sql(cmd)

def tracks_read(user_id):
    cmd = f"select id, title from tracks where user_id = '{user_id}'"
    return sql(cmd)

def tracks_read_title(user_id, title):
    cmd = f"select id from tracks where user_id = '{user_id}' and title = '{title}'"
    return sql(cmd)

def tracks_update_title(user_id, track_id, new_title):
    cmd = f"update tracks set title = '{new_title}' where user_id = '{user_id}' and id = '{track_id}'"
    return sql(cmd)

def tracks_read_id(id):
    cmd = f"select title from tracks where id = '{id}'"
    return sql(cmd)

def tracks_read_all():
    cmd = f"select * from tracks"
    return sql(cmd)