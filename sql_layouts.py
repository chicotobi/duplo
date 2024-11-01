from helpers import sql
from geometry import w0, add_piece

import pandas as pd

# create table pieces (id integer primary key autoincrement, track_id integer not null, idx integer not null, piece varchar(10) not null);
# create table connections (id integer primary key autoincrement, track_id integer not null, p1 integer not null, e1 integer not null, p2 integer not null, e2 integer not null);

# delete from pieces;    
# delete from connections;
# insert into pieces (track_id, idx, piece) values (33, 0, 'straight');
# insert into pieces (track_id, idx, piece) values (33, 1, 'straight'); 
# insert into pieces (track_id, idx, piece) values (33, 2, 'straight'); 
# insert into connections (track_id,p1,e1,p2,e2) values (33,-1,-1,0,0);  
# insert into connections (track_id,p1,e1,p2,e2) values (33, 0, 1,1,0);  
# insert into connections (track_id,p1,e1,p2,e2) values (33, 1, 1,2,0); 

# create table pieces (id int NOT NULL AUTO_INCREMENT, track_id int not null, idx int not null, piece varchar(10) not null, primary key (id));

def pieces_update(track_id, pieces):
    cmd = f"delete from pieces where track_id = '{track_id}'"
    sql(cmd)
    for (idx, piece) in enumerate(pieces):
        cmd = f"insert into pieces (track_id, idx, piece) values ({track_id},{idx},'{piece}')"
        sql(cmd)

def connections_update(track_id, p1a, e1a, p2a, e2a):
    cmd = f"delete from connections where track_id = '{track_id}'"
    sql(cmd)
    for (p1, e1, p2, e2) in zip(p1a,e1a,p2a,e2a):
        cmd = f"insert into connections (track_id, p1, e1, p2, e2) values ({track_id},{p1},{e1},{p2},{e2})"
        sql(cmd)


def pieces_read(track_id):
    cmd = f"select idx, piece from pieces where track_id = '{track_id}' order by idx"
    return sql(cmd)

def connections_read(track_id):
    cmd = f"select p1, e1, p2, e2 from connections where track_id = '{track_id}'"
    return sql(cmd)
    
def pieces_read_all():
    cmd = f"select * from pieces"
    return sql(cmd)

def connections_read_all():
    cmd = f"select * from connections"
    return sql(cmd)

# TODO: In the long run, sql should always return a data.frame with the corresponding columns, even if empty
# But somehow this doesn't work
def layouts_parse(track_id):
    pieces = pd.DataFrame(list(pieces_read(track_id = track_id)))
    if pieces.shape[0] == 0:
        pieces = pd.DataFrame(columns=['idx','piece'])
    connections = pd.DataFrame(list(connections_read(track_id = track_id)))
    if connections.shape[0] == 0:
        connections = pd.DataFrame(columns=['p1','e1','p2','e2'])
    return pieces, connections

def layouts_build(pieces, connections):
    pathes = []
    x0 = 250
    y0 = 250
    zero_position = [(x0 - w0 / 2, y0), (x0 + w0 / 2, y0)]
    all_endings = {-1: [zero_position]}
    for idx, piece in enumerate(pieces):
        tmp = connections[connections.p2 == idx]        
        
        e1 = tmp.e1.values[0]        
        e2 = tmp.e2.values[0]        

        if idx == 0:
            cursor_position = all_endings[-1][0]
        else:
            cursor_position = all_endings[idx-1][e1]

        if piece in ['left', 'right']:
            piece = 'curve'

        pts, endings = add_piece(piece, cursor_position, e2)
        pathes += [pts]
        all_endings[idx] = endings

    return pathes, all_endings

def layouts_free_endings(endings, connections):
    lst = []
    print('---')
    print("connections",connections)
    for piece_idx, ends in endings.items():
        for (ending_idx, end) in enumerate(ends):
            print("piece_idx",piece_idx)
            print("ending_idx",ending_idx)
            # Find if this ending is already in connections
            if any((connections.p1 == piece_idx) & (connections.e1 == ending_idx)):
                continue
            if any((connections.p1 != -1) & (connections.p2 == piece_idx) & (connections.e2 == ending_idx)):
                continue
            lst.append((piece_idx,ending_idx))
    print('---')
    return lst