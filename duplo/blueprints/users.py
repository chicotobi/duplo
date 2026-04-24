"""User account routes: register, login, logout, info, delete."""

from flask import Blueprint, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from ..auth import error, login_required
from ..extensions import limiter
from ..repositories.users import (
    users_create,
    users_delete,
    users_library_read,
    users_read,
    users_read_by_id,
    users_read_hash,
)

bp = Blueprint("users", __name__)


@bp.route("/user_info")
@login_required
def user_info():
    name = users_read_by_id(id=session["user_id"])[0]["name"]
    user_lib = users_library_read(session["user_id"])[0]
    return render_template("user_info.html", name=name, user_lib=user_lib)


@bp.route("/user_register", methods=["GET", "POST"])
@limiter.limit("5 per minute; 30 per hour", exempt_when=lambda: request.method != "POST")
def user_register():
    session.clear()

    if request.method == "GET":
        return render_template("user_register.html")

    if not request.form.get("name"):
        return error("Name missing")
    if not request.form.get("password"):
        return error("Password missing")
    if not request.form.get("confirmation"):
        return error("Repeat password missing")
    if request.form.get("password") != request.form.get("confirmation"):
        return error("Password and repeat password don't match")

    name = request.form.get("name")
    if len(users_read(name)) > 0:
        return error("Name already taken")

    hash = generate_password_hash(request.form.get("password"))
    users_create(name, hash)

    ids = users_read(name)
    session["user_id"] = ids[0]["id"]
    session["user_name"] = name
    return redirect("/")


@bp.route("/user_login", methods=["GET", "POST"])
@limiter.limit("10 per minute; 100 per hour", exempt_when=lambda: request.method != "POST")
def user_login():
    session.clear()

    if request.method == "GET":
        return render_template("user_login.html")

    if not request.form.get("name"):
        return error("Name missing")
    if not request.form.get("password"):
        return error("Password missing")

    name = request.form.get("name")
    hash = users_read_hash(name)
    if len(hash) == 0:
        return error("Name not registered")
    hash = hash[0]["hash"]

    if not check_password_hash(hash, request.form.get("password")):
        return error("Invalid password")

    ids = users_read(name)
    session["user_id"] = ids[0]["id"]
    session["user_name"] = name
    return redirect("/")


@bp.route("/user_delete", methods=["GET", "POST"])
@login_required
def user_delete():
    if request.method == "GET":
        return render_template("user_delete.html")
    users_delete(session["user_id"])
    session.clear()
    return redirect("/")


@bp.route("/user_logout")
def user_logout():
    session.clear()
    return redirect("/")
