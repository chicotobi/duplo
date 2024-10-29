from helpers import sql

# create table users (id integer primary key autoincrement, name text not null, hash text not null);

def users_create(name, hash):
    cmd = f"insert into users (name, hash) values ('{name}','{hash}')"
    return sql(cmd)

def users_read(name):
    cmd = f"select id from users where name = '{name}'"
    return sql(cmd)

def users_read_hash(name):
    cmd = f"select hash from users where name = '{name}'"
    return sql(cmd)

def users_read_all():
    cmd = f"select * from users"
    return sql(cmd)