import os
from functools import wraps

from flask import Flask, render_template, session, redirect
#from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import text

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Session stuff for global variables
#app.config['SESSION_TYPE'] = 'filesystem'
#Session(app)

DEBUG = True

# Database connection
if 'USERNAME' in os.environ.keys() and os.environ['USERNAME'] in ['hofmant3','chicotobi']:
    # Local database in repo for test
    print('Detected local env')
    con_str = 'sqlite:///duplo.db'
else:
    DEBUG = False # No debug in deployed environment
    # Python anywhere MySQL database
    print('Detected pythonanywhere env')
    user = 'chicotobi'
    password = 'qwertzui1'
    host = 'chicotobi.mysql.pythonanywhere-services.com'
    dbname = 'chicotobi$duplo'
    con_str = 'mysql+pymysql://' + user + ':' + password + '@' + host + '/' + dbname
app.config['SQLALCHEMY_DATABASE_URI'] = con_str
db = SQLAlchemy(app)

def sql(cmd):
    if DEBUG:
        print(cmd)
    result = db.session.execute(text(cmd))
    if 'insert' in cmd or 'update' in cmd:
        db.session.commit()
    if 'select' in cmd:
        result = [dict(row._mapping) for row in result]
        if DEBUG:
            print('---')
            print('sql result:')
            print(result)
            print('---')
        return result

def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function

def error(msg):
    return render_template("error.html", msg = msg)