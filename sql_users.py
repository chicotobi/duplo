from helpers import sql

# CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, name text not null, hash text not null,
# n_straights integer, n_curves integer, n_switches integer, n_crossings integer);

# CREATE TABLE users (id int NOT NULL AUTO_INCREMENT, name TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY (id),
# n_straights INT, n_curves INT, n_switches INT, n_crossings INT);

def users_create(name, hash):
    cmd = f"insert into users (name, hash) values ('{name}','{hash}')"
    return sql(cmd)

def users_read(name):
    cmd = f"select id from users where name = '{name}'"
    return sql(cmd)

def users_read_hash(name):
    cmd = f"select hash from users where name = '{name}'"
    return sql(cmd)

def users_delete(user_id):
    sql("PRAGMA foreign_keys=ON")
    cmd = f"delete from users where id = '{user_id}'"
    return sql(cmd)

def users_read_all():
    cmd = f"select * from users"
    return sql(cmd)

def users_library_set(user_id, straights, curves, switches, crossings):
    cmd = f"update users set n_straights = {straights}, n_curves = {curves}, n_switches = {switches}, n_crossings = {crossings} where id = '{user_id}'"
    return sql(cmd)

def users_library_read(user_id):
    cmd = f"select n_straights, n_curves, n_switches, n_crossings from users where id = '{user_id}'"
    return sql(cmd)