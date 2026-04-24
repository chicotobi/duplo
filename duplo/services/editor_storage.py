"""Storage backend for in-progress ``LayoutEditor`` state.

Two backends are supported, selected at runtime by the
``DUPLO_DB_EDITOR_STATE`` Flask config flag:

* ``False`` (default) — state lives in the Flask cookie session, exactly as
  it has historically. The session cookie can grow large for big tracks.
* ``True`` — state lives in the ``editor_states`` table, keyed on
  (user_id, track_id). The session only carries identifiers. Survives
  server restarts and avoids cookie-size limits.

Callers stay unaware of the backend: they only see ``load`` / ``save`` /
``clear`` / ``has_state``.
"""

import json

from flask import current_app, session

from ..repositories.editor_states import (
    editor_state_delete,
    editor_state_read,
    editor_state_upsert,
)
from .editor import LayoutEditor


def _use_db():
    return bool(current_app.config.get("DUPLO_DB_EDITOR_STATE"))


def has_state(user_id, track_id):
    """Return True if there's a resumable editor state for this user/track."""
    if _use_db():
        return editor_state_read(user_id, track_id) is not None
    return all(k in session for k in ("pieces", "connections", "cursor_idx"))


def load(user_id, track_id):
    """Resume an editor session, or initialise from the DB if none exists."""
    if _use_db():
        row = editor_state_read(user_id, track_id)
        if row is None:
            return LayoutEditor.load_from_db(track_id)
        return LayoutEditor.from_session(
            track_id,
            json.loads(row["pieces_json"]),
            json.loads(row["connections_json"]),
            row["cursor_idx"],
        )
    return LayoutEditor.from_session(
        track_id,
        session["pieces"],
        session["connections"],
        session["cursor_idx"],
    )


def save(user_id, editor):
    """Persist transient editor state."""
    state = editor.to_session()
    if _use_db():
        editor_state_upsert(
            user_id=user_id,
            track_id=editor.track_id,
            pieces_json=json.dumps(state["pieces"]),
            connections_json=json.dumps(state["connections"]),
            cursor_idx=state["cursor_idx"],
        )
        # Make sure stale session copies don't shadow the DB on next load.
        for k in ("pieces", "connections", "cursor_idx"):
            session.pop(k, None)
    else:
        session.update(state)


def clear(user_id, track_id):
    """Drop transient state (called on save-and-exit, on track delete, etc.)."""
    if _use_db():
        editor_state_delete(user_id, track_id)
    for k in ("pieces", "connections", "cursor_idx"):
        session.pop(k, None)
