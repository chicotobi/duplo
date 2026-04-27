"""Shared SQLAlchemy extension instance and the low-level ``sql()`` helper."""

from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy.sql import text


db = SQLAlchemy()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://",
)


def sql(cmd, **params):
    """Execute a SQL statement with named bound parameters.

    Use ``:name`` placeholders inside ``cmd`` and pass values as kwargs:

        sql("select id from users where name = :name", name=name)

    For SELECTs returns a list of dict rows; otherwise commits and returns None.
    """
    stmt = text(cmd)
    result = db.session.execute(stmt, params or None)

    lowered = cmd.lstrip().lower()
    if lowered.startswith(("insert", "update", "delete", "pragma")):
        db.session.commit()

    if lowered.startswith("select"):
        rows = [dict(row._mapping) for row in result]
        return rows

    return None
