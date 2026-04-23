import logging
import os
from functools import wraps

from flask import Flask, render_template, session, redirect
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import text


def _build_db_uri():
    """Build the SQLAlchemy DB URI from environment variables.

    Precedence:
      1. ``DUPLO_DATABASE_URI`` if set (full SQLAlchemy URI).
      2. MySQL on PythonAnywhere when ``DUPLO_DB_HOST`` is set.
      3. Local SQLite fallback (``duplo.db`` next to this file).
    """
    uri = os.environ.get("DUPLO_DATABASE_URI")
    if uri:
        return uri

    host = os.environ.get("DUPLO_DB_HOST")
    if host:
        user = os.environ.get("DUPLO_DB_USER", "")
        password = os.environ.get("DUPLO_DB_PASSWORD", "")
        dbname = os.environ.get("DUPLO_DB_NAME", "")
        return f"mysql+pymysql://{user}:{password}@{host}/{dbname}"

    return "sqlite:///duplo.db"


app = Flask(__name__)
app.secret_key = os.environ.get("DUPLO_SECRET_KEY", "dev-only-do-not-use-in-prod")

DEBUG = os.environ.get("DUPLO_DEBUG", "1") == "1"

app.config["SQLALCHEMY_DATABASE_URI"] = _build_db_uri()
db = SQLAlchemy(app)

# Logging: send DEBUG to stderr locally, leave WARNING+ default in production
# (PythonAnywhere captures both stderr and app.logger into the Web tab logs).
_log_level = logging.DEBUG if DEBUG else logging.INFO
app.logger.setLevel(_log_level)

_is_sqlite = app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite")
app.logger.info("Database backend: %s", "sqlite" if _is_sqlite else "mysql")


def sql(cmd, **params):
    """Execute a SQL statement with named bound parameters.

    Use ``:name`` placeholders inside ``cmd`` and pass values as kwargs:

        sql("select id from users where name = :name", name=name)

    For SELECTs returns a list of dict rows; otherwise commits and returns None.
    """
    if "PRAGMA" in cmd and not _is_sqlite:
        return None

    if app.logger.isEnabledFor(logging.DEBUG):
        app.logger.debug("SQL: %s | params=%s", cmd, params)
        db.session.commit()

    stmt = text(cmd)
    result = db.session.execute(stmt, params or None)

    lowered = cmd.lstrip().lower()
    if lowered.startswith(("insert", "update", "delete")) or "pragma" in lowered:
        db.session.commit()

    if lowered.startswith("select"):
        rows = [dict(row._mapping) for row in result]
        if app.logger.isEnabledFor(logging.DEBUG):
            app.logger.debug("SQL result: %s", rows)
        return rows

    return None


def login_required(f):
    """Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/")
        return f(*args, **kwargs)

    return decorated_function


def error(msg):
    return render_template("error.html", msg=msg)
