"""Local development entrypoint.

For production / PythonAnywhere, prefer ``wsgi.py``. This module exists so
``flask --app app run`` and ``from app import app`` both keep working.
"""

from duplo import create_app

app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
