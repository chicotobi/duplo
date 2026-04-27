"""Application factory and configuration loading."""

import logging
import os

from flask import Flask, url_for

from .extensions import csrf, db, limiter


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _build_db_uri():
    """Return the SQLAlchemy database URI.

    Uses ``DUPLO_DATABASE_URI`` if set, otherwise defaults to a local
    SQLite file at ``instance/duplo.db``.
    """
    return os.environ.get(
        "DUPLO_DATABASE_URI",
        "sqlite:///" + os.path.join(_PROJECT_ROOT, "instance", "duplo.db"),
    )


def create_app():
    """Build and configure the Flask app instance."""
    app = Flask(
        "duplo",
        template_folder=os.path.join(_PROJECT_ROOT, "templates"),
        static_folder=os.path.join(_PROJECT_ROOT, "static"),
        instance_path=os.path.join(_PROJECT_ROOT, "instance"),
    )

    app.secret_key = os.environ.get("DUPLO_SECRET_KEY", "dev-only-do-not-use-in-prod")
    app.config["DUPLO_DB_EDITOR_STATE"] = os.environ.get("DUPLO_DB_EDITOR_STATE", "0") == "1"
    app.config["DUPLO_ASSET_VERSION"] = os.environ.get("DUPLO_ASSET_VERSION", "dev")
    app.config["WTF_CSRF_ENABLED"] = os.environ.get("DUPLO_CSRF", "1") == "1"
    app.config["RATELIMIT_ENABLED"] = os.environ.get("DUPLO_RATELIMIT", "1") == "1"
    app.config["SQLALCHEMY_DATABASE_URI"] = _build_db_uri()

    app.logger.setLevel(logging.INFO)

    csrf.init_app(app)
    limiter.init_app(app)

    db.init_app(app)

    @app.context_processor
    def _inject_asset_url():
        version = app.config["DUPLO_ASSET_VERSION"]

        def asset_url(filename):
            return url_for("static", filename=filename) + f"?v={version}"

        return {"asset_url": asset_url}

    from .blueprints.core import bp as core_bp
    from .blueprints.library import bp as library_bp
    from .blueprints.tracks import bp as tracks_bp
    from .blueprints.users import bp as users_bp

    app.register_blueprint(core_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(tracks_bp)
    app.register_blueprint(library_bp)

    return app
