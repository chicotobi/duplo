"""Index/debug routes."""

from flask import Blueprint, current_app, render_template, session

from ..auth import error
from ..repositories.layouts import connections_read_all, pieces_read_all
from ..repositories.tracks import tracks_read_all
from ..repositories.users import users_read_all

bp = Blueprint("core", __name__)


@bp.route("/", methods=["GET", "POST"])
def index():
    debug = current_app.config["DUPLO_DEBUG"]
    if debug:
        users_debug = users_read_all()
        tracks_debug = tracks_read_all()
        pieces_debug = pieces_read_all()
        connections_debug = connections_read_all()
    else:
        users_debug = tracks_debug = pieces_debug = connections_debug = []
    return render_template(
        "index.html",
        DEBUG=debug,
        users_debug=users_debug,
        tracks_debug=tracks_debug,
        pieces_debug=pieces_debug,
        connections_debug=connections_debug,
    )


@bp.route("/debug")
def debug():
    if session.get("user_name") == "tobi":
        return render_template(
            "debug.html",
            users_debug=users_read_all(),
            tracks_debug=tracks_read_all(),
            pieces_debug=pieces_read_all(),
            connections_debug=connections_read_all(),
        )
    return error("Debug only for admin")
