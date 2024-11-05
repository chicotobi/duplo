from helpers import sql
from track_types import zero_position
from geometry import add_piece

import pandas as pd

# --- SQLite
# CREATE TABLE pieces (id INTEGER PRIMARY KEY AUTOINCREMENT, track_id INTEGER NOT NULL, idx INTEGER NOT NULL, piece VARCHAR(10) NOT NULL,
# CONSTRAINT fk_tracks FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE);
# CREATE TABLE connections (id INTEGER PRIMARY KEY AUTOINCREMENT, track_id INTEGER NOT NULL,
# p1 INTEGER NOT NULL,
# e1 INTEGER NOT NULL,
# p2 INTEGER NOT NULL,
# e2 INTEGER NOT NULL,
# CONSTRAINT fk_tracks2 FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE);

# --- MySQL
# CREATE TABLE pieces (id INT NOT NULL AUTO_INCREMENT, track_id INT NOT NULL, idx INT NOT NULL, piece VARCHAR(10) NOT NULL, PRIMARY KEY (id),
# CONSTRAINT fk_tracks FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE);
# CREATE TABLE connections (id INT NOT NULL AUTO_INCREMENT, track_id INT NOT NULL, p1 INT NOT NULL, e1 INT NOT NULL, p2 INT NOT NULL, e2 INT NOT NULL, PRIMARY KEY(id),
# CONSTRAINT fk_tracks2 FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE);

def pieces_update(track_id, pieces):
    cmd = f"delete from pieces where track_id = '{track_id}'"
    sql(cmd)
    for (idx, piece) in enumerate(pieces):
        cmd = f"insert into pieces (track_id, idx, piece) values ({track_id},{idx},'{piece}')"
        sql(cmd)

def connections_update(track_id, connections):
    p1a = connections.p1.values
    e1a = connections.e1.values
    p2a = connections.p2.values
    e2a = connections.e2.values
    cmd = f"delete from connections where track_id = '{track_id}'"
    sql(cmd)
    for (p1, e1, p2, e2) in zip(p1a,e1a,p2a,e2a):
        cmd = f"insert into connections (track_id, p1, e1, p2, e2) values ({track_id},{p1},{e1},{p2},{e2})"
        sql(cmd)

def pieces_read(track_id):
    cmd = f"select piece from pieces where track_id = '{track_id}' order by idx"
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
    pieces = [i['piece'] for i in pieces_read(track_id = track_id)]
    print('pieces',pieces)
    connections = pd.DataFrame(list(connections_read(track_id = track_id)))
    if connections.shape[0] == 0:
        connections = pd.DataFrame(columns=['p1','e1','p2','e2'])
    return pieces, connections

def layouts_build(pieces, connections):
    pathes = []
    all_endings = {-1: [zero_position()]}
    for idx, piece in enumerate(pieces):
        tmp = connections[connections.p2 == idx]        
        
        p1 = tmp.p1.values[0]
        e1 = tmp.e1.values[0]        
        e2 = tmp.e2.values[0]        

        cursor_position = all_endings[p1][e1]

        pts, endings = add_piece(piece, cursor_position, e2)
        pathes += [pts]
        all_endings[idx] = endings

    return pathes, all_endings

def layouts_free_endings(endings, connections):
    lst = []
    for piece_idx, ends in endings.items():
        for (ending_idx, _) in enumerate(ends):
            # Find if this ending is already in connections
            if any((connections.p1 == piece_idx) & (connections.e1 == ending_idx)):
                continue
            if any((connections.p1 != -1) & (connections.p2 == piece_idx) & (connections.e2 == ending_idx)):
                continue
            lst.append((piece_idx,ending_idx))
    # Now the interesting part - what about connections that should be there, because two endings overlap!
    to_be_removed = []
    n = len(lst)
    for i in range(n):
        for j in range(i+1,n):
            p1, e1 = lst[i]
            p2, e2 = lst[j]
            pt1_1, pt1_2 = endings[p1][e1]
            pt2_1, pt2_2 = endings[p2][e2]
            if fitting(pt1_1, pt1_2, pt2_1, pt2_2):
                to_be_removed += [(p1,e1),(p2,e2)]
                print("omg omg omg overlap")

    # Now remove these additional connections
    lst = [i for i in lst if i not in to_be_removed]

    return lst

def fitting(pt1_1, pt1_2, pt2_1, pt2_2):
    res = abs(pt1_1[0] - pt2_2[0]) + abs(pt1_1[1] - pt2_2[1]) + abs(pt1_2[0] - pt2_1[0]) + abs(pt1_2[1] - pt2_1[1])
    return res < 5