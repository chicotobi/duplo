"""Track CRUD + the editor route."""

import os

from flask import Blueprint, redirect, render_template, request, session

from ..auth import error, login_required
from ..repositories.tracks import (
    tracks_create,
    tracks_delete,
    tracks_read,
    tracks_read_id,
    tracks_read_title,
    tracks_update_title,
)
from ..repositories.users import users_library_read
from ..services import editor_storage
from ..services.editor import LayoutEditor
from ..services.thumbnails import (
    delete_thumbnail,
    generate_thumbnail,
    piece_counts,
    thumbnail_file,
    thumbnail_url,
)

bp = Blueprint("tracks", __name__)


@bp.route("/track_create", methods=["POST"])
@login_required
def track_create():
    if not request.form.get("title"):
        return error("Title missing")

    user_id = session["user_id"]
    title = request.form.get("title")
    if len(tracks_read_title(user_id=user_id, title=title)) > 0:
        return error("Title already taken")

    tracks_create(user_id, title)
    track_ids = tracks_read_title(user_id, title)
    session["track_id"] = track_ids[0]["id"]
    session["track_title"] = title
    return redirect("/track_edit")


@bp.route("/track_open", methods=["GET", "POST"])
@login_required
def track_open():
    if request.method == "GET":
        tracks = tracks_read(user_id=session["user_id"])
        track_info = []
        for t in tracks:
            if not os.path.exists(thumbnail_file(t["id"])):
                generate_thumbnail(t["id"])
            track_info.append({
                "id": t["id"],
                "title": t["title"],
                "counts": piece_counts(t["id"]),
                "thumbnail": thumbnail_url(t["id"]),
            })
        return render_template("track_open.html", tracks=track_info)

    if not request.form.get("track_id"):
        return error("Track not selected")
    track_id = request.form.get("track_id")

    session["track_id"] = track_id
    session["track_title"] = tracks_read_id(track_id)[0]["title"]
    return redirect("/track_edit")


@bp.route("/track_rename", methods=["POST"])
@login_required
def track_rename():
    user_id = session["user_id"]
    if not request.form.get("track_id"):
        return error("Track not selected")
    track_id = request.form.get("track_id")
    if not request.form.get("new_title"):
        return error("No new title given")
    new_title = request.form.get("new_title")
    if len(tracks_read_title(user_id, new_title)) > 0:
        return error("Title already taken")

    tracks_update_title(user_id, track_id, new_title)
    return redirect("/track_open")


@bp.route("/track_delete", methods=["POST"])
@login_required
def track_delete():
    user_id = session["user_id"]
    if not request.form.get("track_id"):
        return error("Track not selected")
    track_id = request.form.get("track_id")

    editor_storage.clear(user_id, track_id)
    tracks_delete(user_id, track_id)
    delete_thumbnail(track_id)
    return redirect("/track_open")


@bp.route("/track_edit", methods=["GET", "POST"])
@login_required
def track_edit():
    user_id = session["user_id"]
    track_id = session["track_id"]
    track_title = session["track_title"]

    if request.method == "GET":
        if editor_storage.has_state(user_id, track_id):
            editor = editor_storage.load(user_id, track_id)
        else:
            editor = LayoutEditor.load_from_db(track_id)
        session["user_lib"] = users_library_read(user_id)[0]
    else:
        editor = editor_storage.load(user_id, track_id)

    if request.method == "POST":
        action = next(
            (k for k in request.form.keys() if k != "csrf_token"),
            "",
        )
        if editor.apply_action(action) == "saved":
            editor_storage.clear(user_id, track_id)
            return redirect("/")

    editor_storage.save(user_id, editor)

    user_lib = session["user_lib"]
    return render_template(
        "track_edit.html",
        title=track_title,
        user_lib=user_lib,
        **editor.view_model(user_lib),
    )
