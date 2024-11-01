from helpers import sql
from geometry import w0, add_piece

# create table pieces (id integer primary key autoincrement, track_id integer not null, idx integer not null, piece varchar(10) not null);
# create table connections (id integer primary key autoincrement, track_id integer not null, p1 integer not null, e1 integer not null, p2 integer not null, e2 integer not null);

# create table pieces (id int NOT NULL AUTO_INCREMENT, track_id int not null, idx int not null, piece varchar(10) not null, primary key (id));

def pieces_update(track_id, pieces):
    cmd = f"delete from pieces where track_id = '{track_id}'"
    sql(cmd)
    for (idx, piece) in enumerate(pieces):
        cmd = f"insert into pieces (track_id, idx, piece) values ('{track_id}','{idx}','{piece}')"
        sql(cmd)


def pieces_read(track_id):
    cmd = f"select piece from pieces where track_id = '{track_id}' order by idx"
    return sql(cmd)

    
def pieces_read_all():
    cmd = f"select * from pieces"
    return sql(cmd)

def connections_read_all():
    cmd = f"select * from connections"
    return sql(cmd)


def pieces_parse(track_id):
    layout = pieces_read(track_id = track_id)
    pieces = [i['piece'] for i in layout]
    
    return pieces

def pieces_build(pieces, ending_idxs_last_piece, ending_idxs_new_piece):
    pathes = []
    x0 = 250
    y0 = 250
    all_endings = [[[(x0 - w0 / 2, y0), (x0 + w0 / 2, y0)]]]
    for piece, cursor_idx, ending_idx in zip(pieces, ending_idxs_last_piece, ending_idxs_new_piece):
        cursor_position = all_endings[-1][cursor_idx]
        if piece == 'right':
            type = 'curve'
        elif piece == 'left':
            type = 'curve'        
        else:
            type = piece
        pts, endings = add_piece(type, cursor_position, ending_idx)
        pathes += [pts]
        all_endings += [endings]

    return pathes, all_endings