from helpers import sql
from geometry import w0, add_piece

# create table layouts (id integer primary key autoincrement, track_id integer not null, idx integer not null, tracktype varchar(10) not null);
# create table layouts (id int NOT NULL AUTO_INCREMENT, track_id int not null, idx int not null, tracktype varchar(10) not null, primary key (id));

def layouts_update(track_id, pieces):
    cmd = f"delete from layouts where track_id = '{track_id}'"
    sql(cmd)
    for (idx, piece) in enumerate(pieces):
        cmd = f"insert into layouts (track_id, idx, tracktype) values ('{track_id}','{idx}','{piece}')"
        sql(cmd)


def layouts_read(track_id):
    cmd = f"select tracktype from layouts where track_id = '{track_id}' order by idx"
    return sql(cmd)

    
def layouts_read_all():
    cmd = f"select * from layouts"
    return sql(cmd)


def layouts_parse(track_id):
    layout = layouts_read(track_id = track_id)
    pieces = [i['tracktype'] for i in layout]
    
    return pieces

def layouts_build(pieces):
    pathes = []
    x0 = 250
    y0 = 250
    all_endings = [[[(x0 - w0 / 2, y0), (x0 + w0 / 2, y0)]]]
    for piece in pieces:
        cursor_position = all_endings[-1][0]
        if piece == 'right':
            type = 'curve'
            ending_idx = 1
        elif piece == 'left':
            type = 'curve'
            ending_idx = 0        
        else:
            type = piece
            ending_idx = 0
        pts, endings = add_piece(type, cursor_position, ending_idx)
        pathes += [pts]
        all_endings += [endings]

    return pathes, all_endings