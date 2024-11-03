from helpers import sql

# create table users (id integer primary key autoincrement, name text not null, hash text not null,
# n_straights integer, n_curves integer, n_switches integer, n_crossings integer);

# create table users (id int NOT NULL AUTO_INCREMENT, name text not null, hash text not null, primary key (id));

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