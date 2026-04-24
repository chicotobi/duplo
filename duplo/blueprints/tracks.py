"""Track CRUD + the editor route + JSON action endpoint."""

import os

from flask import Blueprint, jsonify, redirect, render_template, request, session

from ..auth import error, login_required
from ..extensions import limiter
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
    user_id = session["user_id"]
    title = request.form.get("title") or "New track"

    # Deduplicate: append (2), (3), etc. if title exists
    base = title
    n = 1
    while len(tracks_read_title(user_id=user_id, title=title)) > 0:
        n += 1
        title = f"{base} ({n})"

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


@bp.route("/track_edit", methods=["GET"])
@login_required
def track_edit():
    user_id = session["user_id"]
    track_id = session["track_id"]
    track_title = session["track_title"]

    if editor_storage.has_state(user_id, track_id):
        editor = editor_storage.load(user_id, track_id)
    else:
        editor = LayoutEditor.load_from_db(track_id)
    session["user_lib"] = users_library_read(user_id)[0]
    editor_storage.save(user_id, editor)

    user_lib = session["user_lib"]
    return render_template(
        "track_edit.html",
        title=track_title,
        user_lib=user_lib,
        view_model=editor.view_model(user_lib),
        is_anonymous=False,
    )


# --------------------------------------------------------------- JSON actions

def _json_error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


@bp.route("/track_edit/action", methods=["POST"])
@login_required
@limiter.limit("60/second", exempt_when=lambda: request.method != "POST")
def track_edit_action():
    """Apply a single editor action sent as JSON.

    Body: ``{"op": str, ...args}``.
    Returns ``{"ok": true, "view": <view_model>, "extra": {...}}`` on success
    (or ``{"ok": true, "saved": true}`` for the ``save`` op).
    """
    user_id = session["user_id"]
    track_id = session.get("track_id")
    if track_id is None:
        return _json_error("no track selected")

    payload = request.get_json(silent=True) or {}
    op = payload.get("op")
    if not op:
        return _json_error("missing op")

    editor = editor_storage.load(user_id, track_id)
    user_lib = session.get("user_lib") or users_library_read(user_id)[0]
    extra = {}

    try:
        if op == "add_piece":
            pid = editor.add_piece(
                payload["type"],
                float(payload.get("x", 0)),
                float(payload.get("y", 0)),
                int(payload.get("rot", 0)),
                select=bool(payload.get("select", True)),
            )
            extra["piece_id"] = pid
        elif op == "move_piece":
            editor.move_piece(int(payload["piece_id"]),
                              float(payload["x"]),
                              float(payload["y"]),
                              int(payload["rot"]))
        elif op == "commit_move":
            anchor = payload.get("anchor_ending_idx")
            extra.update(editor.commit_move(
                int(payload["piece_id"]),
                float(payload["x"]),
                float(payload["y"]),
                int(payload["rot"]),
                anchor_ending_idx=None if anchor is None else int(anchor),
            ))
        elif op == "rotate_piece":
            editor.rotate_piece(int(payload["piece_id"]),
                                int(payload.get("delta_steps", 1)))
        elif op == "delete_piece":
            editor.delete_piece(int(payload["piece_id"]))
        elif op == "delete_pieces":
            editor.delete_pieces(payload["piece_ids"])
        elif op == "move_pieces":
            editor.move_pieces(payload["moves"])
        elif op == "select":
            ending_idx = payload.get("ending_idx")
            editor.select(int(payload["piece_id"]),
                          None if ending_idx is None else int(ending_idx))
        elif op == "clear_selection":
            editor.clear_selection()
        elif op == "save":
            editor.save()
            editor_storage.clear(user_id, track_id)
            return jsonify({"ok": True, "saved": True})
        elif op == "rename":
            import re
            new_title = (payload.get("title") or "").strip()
            if not new_title or not re.match(r'^[A-Za-z0-9 ()]+$', new_title):
                return _json_error("Invalid title")
            existing = tracks_read_title(user_id, new_title)
            if existing and str(existing[0]["id"]) != str(track_id):
                return _json_error("Title already taken")
            tracks_update_title(user_id, track_id, new_title)
            session["track_title"] = new_title
            return jsonify({"ok": True, "title": new_title})
        else:
            return _json_error(f"unknown op: {op}")
    except (KeyError, ValueError, TypeError) as e:
        return _json_error(str(e))

    editor_storage.save(user_id, editor)
    return jsonify({
        "ok": True,
        "view": editor.view_model(user_lib),
        "extra": extra,
    })
