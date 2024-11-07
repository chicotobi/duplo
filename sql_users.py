from helpers import sql

# --- SQLite
# CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, hash TEXT NOT NULL,
# straight INTEGER, curve INTEGER, switch INTEGER, crossing INTEGER);

# --- MySQL
# CREATE TABLE users (id int NOT NULL AUTO_INCREMENT, name TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY (id),
# straight INT, curve INT, switch INT, crossing INT);

def users_create(name, hash):
    cmd = f"insert into users (name, hash, straight, curve, switch, crossing) values ('{name}','{hash}',99,99,99,99)"
    return sql(cmd)

def users_read(name):
    cmd = f"select id from users where name = '{name}'"
    return sql(cmd)

def users_read_by_id(id):
    cmd = f"select id, name from users where id = '{id}'"
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

def users_library_set(user_id, straight, curve, switch, crossing):
    cmd = f"update users set straight = {straight}, curve = {curve}, switch = {switch}, crossing = {crossing} where id = '{user_id}'"
    return sql(cmd)

def users_library_read(user_id):
    cmd = f"select straight, curve, switch, crossing from users where id = '{user_id}'"
    return sql(cmd)