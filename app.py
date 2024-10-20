from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy

from sqlalchemy.sql import text

from geometry import add_curve_left, add_curve_right, add_straight, w0, get_front_arrow

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///duplo.db'
db = SQLAlchemy(app)

ts = []
pathes = []
x0 = 250
y0 = 250

cur_pos = [[(x0 + w0 / 2, y0), (x0 - w0 / 2, y0)]]

class tracks(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tracktype = db.Column(db.String(1))
    def __repr__(self):
        return f'{self.id}>'
    
def sql(cmd):
    return db.session.execute(text(cmd))

def save(ts):
    sql("delete from tracks")
    for t in ts:
        new_track = tracks(tracktype = t)
        db.session.add(new_track)
    db.session.commit()

def load():
    ts = list(sql("select tracktype from tracks"))
    print(ts)

    # Now build path
    pathes = []
    cur_pos = [[(x0 + w0 / 2, y0), (x0 - w0 / 2, y0)]]
    for val in ts:
        if val == 'left':
            pts, endings = add_curve_left(cur_pos)
        elif val == 'straight':
            pts, endings = add_straight(cur_pos)
        elif val == 'right':
            pts, endings = add_curve_right(cur_pos)
        path += [pts]
        cur_pos += [endings[-1]]

    return ts, pathes, cur_pos

@app.route('/', methods=['GET', 'POST'])
def index():
    global ts, pathes, cur_pos
    print('ts',ts)
    print('path',pathes)
    print('cur_pos',cur_pos[-1])
    if request.method == 'POST':
        val = list(request.form.keys())[0]
        if val in ['left','straight','right']:
            ts.append(val)
            if val == 'left':
                pts, endings = add_curve_left(cur_pos[-1])
            elif val == 'straight':
                pts, endings = add_straight(cur_pos[-1])
            elif val == 'right':
                pts, endings = add_curve_right(cur_pos[-1])
            pathes += [pts]
            cur_pos += [endings[-1]]
        elif val == 'delete':
            if len(ts) > 0:
                 ts = ts[:-1]
                 pathes.pop()
                 cur_pos.pop()
        elif val == 'save':
            save(ts)
        elif val == 'load':
            ts, pathes, cur_pos = load()

    path = pathes + [get_front_arrow(cur_pos[-1])]

    return render_template('index.html', path = path , tracks = ts)