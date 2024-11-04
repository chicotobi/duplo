from flask import request, render_template, session, redirect, url_for

from werkzeug.security import check_password_hash, generate_password_hash

from geometry import get_path_cursor
from helpers import login_required, app, error, DEBUG
from sql_users import users_create, users_read, users_read_hash, users_read_all, users_delete, users_library_set, users_library_read
from sql_tracks import tracks_create, tracks_read, tracks_read_title, tracks_read_id, tracks_read_all, tracks_update_title, tracks_delete
from sql_layouts import pieces_update, connections_update, layouts_parse, pieces_read_all, connections_read_all, layouts_build, layouts_free_endings

import pandas as pd

@app.route("/", methods=["GET", "POST"])
def index():
    if DEBUG:
        users_debug = users_read_all()
        tracks_debug = tracks_read_all()
        pieces_debug = pieces_read_all()
        connections_debug = connections_read_all()
    else:
        users_debug = tracks_debug = pieces_debug = connections_debug = []
    return render_template('index.html', DEBUG = DEBUG, users_debug = users_debug, tracks_debug = tracks_debug, pieces_debug = pieces_debug, connections_debug = connections_debug)

@app.route("/track_create", methods=["GET", "POST"])
@login_required
def track_create():    
    if request.method == "GET":
        return render_template("track_create.html")
    
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

    return redirect("/track_edit")


@app.route("/track_open", methods=["GET", "POST"])
@login_required
def track_open():    
    if request.method == "GET":
        # Get available tracks for this user
        tracks = tracks_read(user_id = session['user_id'])
        return render_template("track_open.html", tracks = tracks)
    
    # Input check
    if not request.form.get("track_id"):
        return error("Track not selected")
    track_id = request.form.get("track_id")
    
    session['track_id'] = track_id
    titles = tracks_read_id(track_id)
    session['track_title'] = titles[0]["title"]

    return redirect("/track_edit")

@app.route("/track_rename", methods=["GET", "POST"])
@login_required
def track_rename():    
    user_id = session['user_id']
    if request.method == "GET":
        # Get available tracks for this user
        tracks = tracks_read(user_id)
        return render_template("track_rename.html", tracks = tracks)
    
    # Input check
    if not request.form.get("track_id"):
        return error("Track not selected")
    track_id = request.form.get("track_id")
    if not request.form.get("new_title"):
        return error("No new title given")
    new_title = request.form.get("new_title")
    tracks = tracks_read_title(user_id, new_title)
    if len(tracks) > 0:
        return error("Title already taken")
    
    tracks_update_title(user_id, track_id, new_title)

    return redirect("/")

@app.route("/track_delete", methods=["GET", "POST"])
@login_required
def track_delete():    
    user_id = session['user_id']
    if request.method == "GET":
        # Get available tracks for this user
        tracks = tracks_read(user_id)
        return render_template("track_delete.html", tracks = tracks)
    
    # Input check
    if not request.form.get("track_id"):
        return error("Track not selected")
    track_id = request.form.get("track_id")
    
    tracks_delete(user_id, track_id)

    return redirect("/")

@app.route('/track_edit', methods=['GET', 'POST'])
@login_required
def edit():
    track_id = session['track_id']
    track_title = session['track_title']

    if request.method == 'GET':
        # Initialize from database
        pieces, connections = layouts_parse(track_id)
        pieces = pieces['piece'].to_list()
        pathes, endings = layouts_build(pieces, connections)
        session['pieces'] = pieces
        session['connections'] = connections.to_dict(orient = 'records')
        session['cursor_idx'] = 0
        
        user_lib = users_library_read(session['user_id'])[0]
        if 'n_straights' not in user_lib.keys():
            user_lib['n_straights'] = 99
            user_lib['n_curves'   ] = 99
            user_lib['n_switches' ] = 99
            user_lib['n_crossings'] = 99
        session['user_lib'] = user_lib
    
    # Set scope variables from session variables
    pieces = session['pieces']
    connections = pd.DataFrame(session['connections'])
    if connections.shape[0] == 0:
        connections = pd.DataFrame(columns=['p1','e1','p2','e2'])
    cursor_idx = session['cursor_idx']
    
    _, endings = layouts_build(pieces, connections) 

    free_endings = layouts_free_endings(endings,connections)
    print('free_endings',free_endings)

    lib1 = {v:sum(1 for i in pieces if i == v) for v in ['straight','curve','switch','crossing']}
    lib = {**lib1, **session['user_lib']}

    # Logic works with the scoped variables
    if request.method == 'POST':
        val = list(request.form.keys())[0]
        if val in ['left','straight','right','switch','crossing']:
            if (
                (val in ['straight'    ] and lib['straight'] < lib['n_straights']) or
                (val in ['left','right'] and lib['curve'   ] < lib['n_curves'   ]) or
                (val in ['switch'      ] and lib['switch'  ] < lib['n_switches' ]) or
                (val in ['crossing'    ] and lib['crossing'] < lib['n_crossings'])
                ):
                p1 = free_endings[cursor_idx][0]
                e1 = free_endings[cursor_idx][1]
                p2 = len(pieces)
                if val == 'right':
                    e2 = 1
                else:
                    e2 = 0
                cursor_idx = 0
                if val in ['left','right']:
                    val = 'curve'
                pieces.append(val)
                new_connections_row = pd.DataFrame([{'p1':p1,'e1':e1,'p2':p2,'e2':e2}])
                connections = pd.concat([connections,new_connections_row])
        elif val == 'delete':
            if len(pieces) > 0:
                pieces.pop()
                # Remove all registered connections
                connections = connections[connections.p1 != len(pieces)]
                connections = connections[connections.p2 != len(pieces)]
                cursor_idx = 0
        elif val == 'next_ending':
            if len(free_endings) > 0:
                cursor_idx = (cursor_idx + 1) % len(free_endings)
        elif val == 'rotate':
            if len(pieces) > 0:
                # Get the index of the current element
                current_piece = len(pieces) - 1

                # Number of endings for this piece
                n = len(endings[current_piece])

                # Now get the current ending idx
                current_ending = connections[connections.p2 == current_piece].e2.values[0]

                # Now increase this index
                current_ending = (current_ending + 1) % n

                # Now set the increased ending idx
                connections.loc[connections.p2 == current_piece,'e2'] = current_ending
        elif val == 'save':
            pieces_update(track_id = track_id, pieces = pieces)
            connections_update(track_id = track_id, p1a = connections.p1.values, e1a = connections.e1.values, p2a = connections.p2.values, e2a = connections.e2.values)
            return redirect("/")

    lib1 = {v:sum(1 for i in pieces if i == v) for v in ['straight','curve','switch','crossing']}
    lib = {**lib1, **session['user_lib']}

    # Set session variables from scope variables
    session['pieces'] = pieces
    session['connections'] = connections.to_dict(orient = 'records')
    session['cursor_idx'] = cursor_idx
        
    path, endings = layouts_build(pieces, connections) 

    free_endings = layouts_free_endings(endings,connections)

    current_ending = free_endings[cursor_idx]
    cursor = endings[current_ending[0]][current_ending[1]]
    
    if len(free_endings) > 0:            
        path_cursor = get_path_cursor(cursor)
        path += [path_cursor]


    return render_template('track_edit.html', title = track_title, path = path, lib = lib)

@app.route("/library_set", methods=["GET", "POST"])
@login_required
def library_set():    
    user_id = session['user_id']


    user_lib = users_library_read(session['user_id'])[0]
    if 'n_straights' not in user_lib.keys():
        user_lib['n_straights'] = 99
        user_lib['n_curves'   ] = 99
        user_lib['n_switches' ] = 99
        user_lib['n_crossings'] = 99

    if request.method == "GET":
        # Get available tracks for this user
        return render_template("library_set.html", lib = user_lib)
    
    # Input check
    if not request.form.get("straights"):
        return error("Straight not set")
    if not request.form.get("curves"):
        return error("Curves not set")
    if not request.form.get("switches"):
        return error("Switches not set")
    if not request.form.get("crossings"):
        return error("Crossings not set")
    
    straights = request.form.get("straights")
    curves    = request.form.get("curves")
    switches  = request.form.get("switches")
    crossings = request.form.get("crossings")
    
    users_library_set(user_id, straights, curves, switches, crossings)

    return redirect("/")

@app.route("/user_register", methods=["GET", "POST"])
def user_register():
    # Forget any user_id
    session.clear()

    if request.method == "GET":
        return render_template("user_register.html")

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


@app.route("/user_login", methods=["GET", "POST"])
def user_login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    if request.method == "GET":
        return render_template("user_login.html")

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
    
@app.route("/user_delete", methods=["GET", "POST"])
@login_required
def user_delete():    
    user_id = session['user_id']
    if request.method == "GET":
        return render_template("user_delete.html")
        
    users_delete(user_id)
    session.clear()
    return redirect("/")

@app.route("/user_logout")
def user_logout():
    session.clear()
    return redirect("/")
