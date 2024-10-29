from flask import request, render_template, session, redirect, url_for

from werkzeug.security import check_password_hash, generate_password_hash

from geometry import add_curve_left, add_curve_right, add_straight, w0, get_front_arrow
from helpers import login_required, app, error, DEBUG
from sql_users import users_create, users_read, users_read_hash, users_read_all
from sql_tracks import tracks_create, tracks_read, tracks_read_title, tracks_read_id, tracks_read_all
from sql_layouts import layouts_update, layouts_parse, layouts_read_all, layouts_build

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    user_id = session["user_id"]
    tracks = tracks_read(user_id = user_id)
    if DEBUG:
        users_debug = users_read_all()
        tracks_debug = tracks_read_all()
        layouts_debug = layouts_read_all()
    else:
        users_debug = tracks_debug = layouts_debug = []
    return render_template('index.html', tracks = tracks, users_debug = users_debug, tracks_debug = tracks_debug, layouts_debug = layouts_debug)

@app.route("/create", methods=["GET", "POST"])
@login_required
def create():    
    if request.method == "GET":
        return render_template("create.html")
    
    # Input check
    if not request.form.get("title"):
        return error("Title missing")

    # Title already taken?
    user_id = session["user_id"]
    title = request.form.get("title")
    tracks = tracks_read_title(user_id = user_id, title = title)
    if len(tracks) > 0:
        return error("Title already taken")

    # Save to database
    tracks_create(user_id, title)

    # Remember which track_id is edited
    track_ids = tracks_read_title(user_id, title)
    session['track_id'] = track_ids[0]["id"]
    session['track_title'] = title

    return redirect("/edit")


@app.route("/open", methods=["GET", "POST"])
@login_required
def open():    
    if request.method == "GET":
        # Get available tracks for this user
        tracks = tracks_read(user_id = session['user_id'])
        return render_template("open.html", tracks = tracks)
    
    # Input check
    if not request.form.get("track_id"):
        return error("Track not selected")
    track_id = request.form.get("track_id")
    
    session['track_id'] = track_id
    titles = tracks_read_id(track_id)
    session['track_title'] = titles[0]["title"]

    return redirect("/edit")


@app.route('/edit', methods=['GET', 'POST'])
@login_required
def edit():
    track_id = session['track_id']
    track_title = session['track_title']

    if request.method == 'GET':
        # Initialize from database
        tracktypes = layouts_parse(track_id)
        session['tracktypes'] = tracktypes
    
    # Set scope variables from session variables
    tracktypes = session['tracktypes']

    if DEBUG:
        print('tracktypes',tracktypes)
    
    # Logic works with the scoped variables
    if request.method == 'POST':
        val = list(request.form.keys())[0]
        if val in ['left','straight','right']:
            tracktypes.append(val)
        elif val == 'delete':
            if len(tracktypes) > 0:
                tracktypes.pop()
        elif val == 'save':
            layouts_update(track_id = track_id, tracktypes = tracktypes)
            return redirect("/")

    # Set session variables from scope variables
    session['tracktypes'] = tracktypes
    pathes, cur_pos = layouts_build(tracktypes)

    return render_template('edit.html', title = track_title, path = pathes + [get_front_arrow(cur_pos[-1])] , tracks = tracktypes)


@app.route("/register", methods=["GET", "POST"])
def register():
    # Forget any user_id
    session.clear()

    if request.method == "GET":
        return render_template("register.html")

    # Input check
    if not request.form.get("name"):
        return error("Name missing")
    elif not request.form.get("password"):
        return error("Password missing")
    elif not request.form.get("confirmation"):
        return error("Repeat password missing")
    if request.form.get("password") != request.form.get("confirmation"):
        return error("Password and repeat password don't match")

    # Name already taken?
    name = request.form.get("name")
    ids = users_read(name)
    if len(ids) > 0:
        return error("Name already taken")

    # Save to database
    hash = generate_password_hash(request.form.get("password"))
    users_create(name, hash)

    # Remember which user has logged in
    ids = users_read(name)
    session["user_id"] = ids[0]["id"]

    return redirect("/")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    if request.method == "GET":
        return render_template("login.html")

    # Input check
    if not request.form.get("name"):
        return error("Name missing")
    elif not request.form.get("password"):
        return error("Password missing")

    # Find hash has logged in
    name = request.form.get("name")
    hash = users_read_hash(name)
    if len(hash) == 0:
        return error("Name not registered")
    hash = hash[0]["hash"]

    # Check password
    password = request.form.get("password")
    if not check_password_hash(hash, password):
        return error("Invalid password")

    # Remember which user has logged in
    ids = users_read(name)
    session["user_id"] = ids[0]["id"]

    return redirect("/")

    
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")
