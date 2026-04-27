"""Index route + anonymous sandbox editor."""

from flask import Blueprint, jsonify, redirect, render_template, request, session

from ..extensions import limiter
from ..services.editor import LayoutEditor

bp = Blueprint("core", __name__)

# Default library for anonymous sandbox
_DEFAULT_LIB = {"straight": 8, "curve": 12, "switch": 2, "crossing": 1}


@bp.route("/", methods=["GET", "POST"])
def index():
    if session.get("user_id"):
        return redirect("/track_open")

    # Anonymous sandbox editor
    editor = _load_sandbox()
    return render_template(
        "track_edit.html",
        title="Sandbox",
        user_lib=_DEFAULT_LIB,
        view_model=editor.view_model(_DEFAULT_LIB),
        is_anonymous=True,
        room_w=6,
        room_h=4,
    )


def _load_sandbox():
    """Load or create the anonymous sandbox editor from session."""
    if session.get("sandbox_pieces") is not None:
        return LayoutEditor.from_session(
            track_id=0,
            pieces=session["sandbox_pieces"],
            selection=session.get("sandbox_selection"),
            next_provisional_id=session.get("sandbox_next_id", -1),
        )
    return LayoutEditor(track_id=0, pieces=[])


def _save_sandbox(editor):
    """Persist sandbox editor state into the session."""
    state = editor.to_session()
    session["sandbox_pieces"] = state["pieces"]
    session["sandbox_selection"] = state["selection"]
    session["sandbox_next_id"] = state["next_provisional_id"]


@bp.route("/sandbox/action", methods=["POST"])
@limiter.limit("60/second", exempt_when=lambda: request.method != "POST")
def sandbox_action():
    """Editor actions for the anonymous sandbox. Same protocol as track_edit/action."""
    payload = request.get_json(silent=True) or {}
    op = payload.get("op")
    if not op:
        return jsonify({"ok": False, "error": "missing op"}), 400

    if op in ("save", "rename"):
        return jsonify({"ok": False, "login_required": True})

    editor = _load_sandbox()
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
        else:
            return jsonify({"ok": False, "error": f"unknown op: {op}"}), 400
    except (KeyError, ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    _save_sandbox(editor)
    return jsonify({
        "ok": True,
        "view": editor.view_model(_DEFAULT_LIB),
        "extra": extra,
    })
