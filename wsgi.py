"""WSGI entrypoint for production (PythonAnywhere).

In the PA WSGI file, after setting environment variables:

    from wsgi import application
"""

from duplo import create_app

application = create_app()
