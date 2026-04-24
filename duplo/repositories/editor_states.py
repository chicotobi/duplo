"""Repository for the ``editor_states`` table (server-side editor autosave)."""

from ..extensions import sql


def editor_state_read(user_id, track_id):
    """Return the saved editor state for (user, track) or ``None``."""
    rows = sql(
        "SELECT pieces_json, connections_json, cursor_idx "
        "FROM editor_states WHERE user_id = :user_id AND track_id = :track_id",
        user_id=user_id,
        track_id=track_id,
    )
    return rows[0] if rows else None


def editor_state_upsert(user_id, track_id, pieces_json, connections_json, cursor_idx):
    """Insert or replace the editor state for (user, track).

    Implemented as delete-then-insert to stay portable across sqlite and mysql
    without needing dialect-specific ON CONFLICT / ON DUPLICATE KEY syntax.
    """
    sql(
        "DELETE FROM editor_states WHERE user_id = :user_id AND track_id = :track_id",
        user_id=user_id,
        track_id=track_id,
    )
    sql(
        "INSERT INTO editor_states "
        "(user_id, track_id, pieces_json, connections_json, cursor_idx) "
        "VALUES (:user_id, :track_id, :pieces_json, :connections_json, :cursor_idx)",
        user_id=user_id,
        track_id=track_id,
        pieces_json=pieces_json,
        connections_json=connections_json,
        cursor_idx=cursor_idx,
    )


def editor_state_delete(user_id, track_id):
    sql(
        "DELETE FROM editor_states WHERE user_id = :user_id AND track_id = :track_id",
        user_id=user_id,
        track_id=track_id,
    )
