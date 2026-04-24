"""Storage backend for in-progress ``LayoutEditor`` state.

Two backends, selected by the ``DUPLO_DB_EDITOR_STATE`` Flask config flag:

* ``False`` (default) — Flask cookie session. Cookie can grow large.
* ``True`` — ``editor_states`` table keyed on (user_id, track_id). Survives
  restarts and avoids cookie-size limits.
"""

import json

from flask import current_app, session

from ..repositories.editor_states import (
    editor_state_delete,
    editor_state_read,
    editor_state_upsert,
)
from .editor import LayoutEditor


_SESSION_KEYS = ("pieces", "selection", "next_provisional_id", "editor_track_id")


def _use_db():
    return bool(current_app.config.get("DUPLO_DB_EDITOR_STATE"))


def has_state(user_id, track_id):
    if _use_db():
        return editor_state_read(user_id, track_id) is not None
    if "pieces" not in session:
        return False
    return session.get("editor_track_id") == track_id


def load(user_id, track_id):
    if _use_db():
        row = editor_state_read(user_id, track_id)
        if row is None:
            return LayoutEditor.load_from_db(track_id)
        sel = json.loads(row["selection_json"]) if row["selection_json"] else None
        return LayoutEditor.from_session(
            track_id,
            json.loads(row["pieces_json"]),
            sel,
            next_provisional_id=-1,
        )
    if session.get("editor_track_id") != track_id:
        return LayoutEditor.load_from_db(track_id)
    return LayoutEditor.from_session(
        track_id,
        session.get("pieces", []),
        session.get("selection"),
        next_provisional_id=session.get("next_provisional_id", -1),
    )


def save(user_id, editor):
    state = editor.to_session()
    if _use_db():
        editor_state_upsert(
            user_id=user_id,
            track_id=editor.track_id,
            pieces_json=json.dumps(state["pieces"]),
            selection_json=json.dumps(state["selection"]) if state["selection"] else None,
        )
        for k in _SESSION_KEYS:
            session.pop(k, None)
    else:
        session["pieces"] = state["pieces"]
        session["selection"] = state["selection"]
        session["next_provisional_id"] = state["next_provisional_id"]
        session["editor_track_id"] = editor.track_id


def clear(user_id, track_id):
    if _use_db():
        editor_state_delete(user_id, track_id)
    for k in _SESSION_KEYS:
        session.pop(k, None)
