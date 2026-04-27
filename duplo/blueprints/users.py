"""User account routes: register, login, logout, info, delete."""

from flask import Blueprint, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from ..auth import error, login_required
from ..extensions import limiter
from ..repositories.tracks import tracks_create, tracks_read_title
from ..repositories.users import (
    users_create,
    users_delete,
    users_library_read,
    users_read,
    users_read_by_id,
    users_read_hash,
    users_room_read,
    users_room_set,
)
from ..services import editor_storage
from ..services.editor import LayoutEditor

bp = Blueprint("users", __name__)


@bp.route("/user_info")
@login_required
def user_info():
    name = users_read_by_id(id=session["user_id"])[0]["name"]
    user_lib = users_library_read(session["user_id"])[0]
    room = users_room_read(session["user_id"])[0]
    return render_template("user_info.html", name=name, user_lib=user_lib, room=room)


@bp.route("/user_register", methods=["GET", "POST"])
@limiter.limit("5 per minute; 30 per hour", exempt_when=lambda: request.method != "POST")
def user_register():
    # Preserve sandbox state across session.clear()
    sandbox_pieces = session.get("sandbox_pieces")
    sandbox_selection = session.get("sandbox_selection")
    sandbox_next_id = session.get("sandbox_next_id", -1)

    session.clear()

    if request.method == "GET":
        # Carry sandbox forward so it survives the GET→POST round-trip
        if sandbox_pieces:
            session["sandbox_pieces"] = sandbox_pieces
            session["sandbox_selection"] = sandbox_selection
            session["sandbox_next_id"] = sandbox_next_id
        return render_template("user_register.html")

    if not request.form.get("name"):
        return error("Name missing")
    if not request.form.get("password"):
        return error("Password missing")
    if not request.form.get("confirmation"):
        return error("Repeat password missing")
    if request.form.get("password") != request.form.get("confirmation"):
        return error("Password and repeat password don't match")

    name = request.form.get("name")
    if len(users_read(name)) > 0:
        return error("Name already taken")

    hash = generate_password_hash(request.form.get("password"))
    users_create(name, hash)

    ids = users_read(name)
    session["user_id"] = ids[0]["id"]
    session["user_name"] = name

    # Adopt sandbox track into the new account
    sandbox_pieces = sandbox_pieces or session.get("sandbox_pieces")
    if sandbox_pieces:
        _adopt_sandbox(ids[0]["id"], sandbox_pieces, sandbox_selection, sandbox_next_id)

    return redirect("/")


@bp.route("/user_login", methods=["GET", "POST"])
@limiter.limit("10 per minute; 100 per hour", exempt_when=lambda: request.method != "POST")
def user_login():
    session.clear()

    if request.method == "GET":
        return render_template("user_login.html")

    if not request.form.get("name"):
        return error("Name missing")
    if not request.form.get("password"):
        return error("Password missing")

    name = request.form.get("name")
    hash = users_read_hash(name)
    if len(hash) == 0:
        return error("Name not registered")
    hash = hash[0]["hash"]

    if not check_password_hash(hash, request.form.get("password")):
        return error("Invalid password")

    ids = users_read(name)
    session["user_id"] = ids[0]["id"]
    session["user_name"] = name
    return redirect("/")


def _adopt_sandbox(user_id, pieces, selection, next_id):
    """Create a track from sandbox pieces for a newly registered user."""
    title = "Sandbox"
    tracks_create(user_id, title)
    row = tracks_read_title(user_id, title)
    track_id = row[0]["id"]

    editor = LayoutEditor.from_session(
        track_id=track_id,
        pieces=pieces,
        selection=selection,
        next_provisional_id=next_id,
    )
    editor.save()
    editor_storage.save(user_id, editor)

    session["track_id"] = track_id
    session["track_title"] = title


@bp.route("/user_delete", methods=["GET", "POST"])
@login_required
def user_delete():
    if request.method == "GET":
        return render_template("user_delete.html")
    users_delete(session["user_id"])
    session.clear()
    return redirect("/")


@bp.route("/user_logout")
def user_logout():
    session.clear()
    return redirect("/")
