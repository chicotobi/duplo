"""Auth helpers: login_required decorator and the ``error()`` shortcut."""

from functools import wraps

from flask import redirect, render_template, session


def login_required(f):
    """Redirect to the index if the user is not logged in."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/")
        return f(*args, **kwargs)

    return decorated_function


def error(msg):
    return render_template("error.html", msg=msg)
