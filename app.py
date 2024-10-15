from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy

from sqlalchemy.sql import text

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///duplo.db'
db = SQLAlchemy(app)

class tracks(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tracktype = db.Column(db.String(1))
    def __repr__(self):
        return f'{self.id}>'
    
def add_track(tracktype0):
    new_track = tracks(tracktype = tracktype0)
    db.session.add(new_track)
    db.session.commit()

def remove_last_track():
    last_track = tracks.query.order_by(tracks.id.desc()).first()
    if last_track:
        db.session.delete(last_track)
        db.session.commit()

def sql(cmd):
    return db.session.execute(text(cmd))

@app.route('/', methods=['GET', 'POST'])
def hello_world():
    cmd = "select tracktype from tracks"
    tracks = sql(cmd)
    if request.method == 'POST':
        val = list(request.form.keys())[0]
        print(val)
        if val in ['left','straight','right']:
            add_track(val)
        elif val == 'delete':
            remove_last_track()
        cmd = "select tracktype from tracks"
        tracks = sql(cmd)

    tracks = list(tracks)

    circle_properties = {
        'centerX': 250,
        'centerY': 250,
        'radius': 10 * len(tracks),
        'color': 'blue',
        'border_color': 'black',
        'border_width': 2
    }

    return render_template('index.html', tracks = tracks, circle = circle_properties)