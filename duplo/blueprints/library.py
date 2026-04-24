"""Library (piece inventory) routes."""

from flask import Blueprint, redirect, render_template, request, session

from ..auth import error, login_required
from ..repositories.users import users_library_read, users_library_set

bp = Blueprint("library", __name__)


@bp.route("/library_set", methods=["GET", "POST"])
@login_required
def library_set():
    user_id = session["user_id"]
    user_lib = users_library_read(session["user_id"])[0]

    if request.method == "GET":
        return render_template("library_set.html", user_lib=user_lib)

    if not request.form.get("straight"):
        return error("Straight not set")
    if not request.form.get("curve"):
        return error("Curve not set")
    if not request.form.get("switch"):
        return error("Switch not set")
    if not request.form.get("crossing"):
        return error("Crossing not set")

    users_library_set(
        user_id,
        request.form.get("straight"),
        request.form.get("curve"),
        request.form.get("switch"),
        request.form.get("crossing"),
    )
    return redirect("/")
