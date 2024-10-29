from helpers import sql
from geometry import w0, add_curve_left, add_curve_right, add_straight

# create table layouts (id integer primary key autoincrement, track_id integer not null, idx integer not null, tracktype varchar(10) not null);

def layouts_update(track_id, tracktypes):
    cmd = f"delete from layouts where track_id = '{track_id}'"
    sql(cmd)
    for (idx, tracktype) in enumerate(tracktypes):
        cmd = f"insert into layouts (track_id, idx, tracktype) values ('{track_id}','{idx}','{tracktype}')"
        sql(cmd)


def layouts_read(track_id):
    cmd = f"select idx, tracktype from layouts where track_id = '{track_id}'"
    return sql(cmd)

    
def layouts_read_all():
    cmd = f"select * from layouts"
    return sql(cmd)


def layouts_parse(track_id):
    layout = layouts_read(track_id = track_id)
    print(layout)

    layout = {v['idx']:v['tracktype'] for v in layout}
    print(layout)

    # Now build path
    n = len(layout)
    ts = []
    pathes = []
    x0 = 250
    y0 = 250
    cur_pos = [[(x0 + w0 / 2, y0), (x0 - w0 / 2, y0)]]
    for i in range(n):
        val = layout[i]
        ts.append(val)
        if val == 'left':
            pts, endings = add_curve_left(cur_pos[-1])
        elif val == 'straight':
            pts, endings = add_straight(cur_pos[-1])
        elif val == 'right':
            pts, endings = add_curve_right(cur_pos[-1])
        else:
            print('bug')
        pathes += [pts]
        cur_pos += [endings[-1]]
    print(ts)
    return ts, pathes, cur_pos