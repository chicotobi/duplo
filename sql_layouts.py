from helpers import sql
from geometry import w0, add_piece

# create table layouts (id integer primary key autoincrement, track_id integer not null, idx integer not null, tracktype varchar(10) not null);
# create table layouts (id int NOT NULL AUTO_INCREMENT, track_id int not null, idx int not null, tracktype varchar(10) not null, primary key (id));

def layouts_update(track_id, tracktypes):
    cmd = f"delete from layouts where track_id = '{track_id}'"
    sql(cmd)
    for (idx, tracktype) in enumerate(tracktypes):
        cmd = f"insert into layouts (track_id, idx, tracktype) values ('{track_id}','{idx}','{tracktype}')"
        sql(cmd)


def layouts_read(track_id):
    cmd = f"select tracktype from layouts where track_id = '{track_id}' order by idx"
    return sql(cmd)

    
def layouts_read_all():
    cmd = f"select * from layouts"
    return sql(cmd)


def layouts_parse(track_id):
    layout = layouts_read(track_id = track_id)
    tracktypes = [i['tracktype'] for i in layout]
    
    return tracktypes

def layouts_build(tracktypes):
    pathes = []
    x0 = 250
    y0 = 250
    cur_pos = [[(x0 - w0 / 2, y0), (x0 + w0 / 2, y0)]]
    for tracktype in tracktypes:
        if tracktype == 'left':
            pts, endings = add_piece('curve',cur_pos[-1], 0)
        elif tracktype == 'straight':
            pts, endings = add_piece('straight',cur_pos[-1], 0)
        elif tracktype == 'right':
            pts, endings = add_piece('curve',cur_pos[-1], 1)
        elif tracktype == 'switch':
            pts, endings = add_piece('switch',cur_pos[-1], 0)
        else:
            raise
        pathes += [pts]
        cur_pos += [endings[-1]]

    return pathes, cur_pos