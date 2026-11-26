import os, json
import re
from datetime import datetime
from markupsafe import Markup, escape
from flask import Flask, render_template, request, session
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from datetime import timedelta
from backend.models.users import User
from backend.extensions import db, csrf, limiter
from backend.models.devices import Device
from backend.models.credentials import Credential
from backend.utils.setup_users import initialize_default_users
from backend.utils.db_upgrade import check_and_upgrade_database, upgrade_feature_columns
from backend.app_security import init_security
from backend.utils import paths
from backend import app_setup, features
from backend.integrations import models as _integration_models  # noqa: F401  (registers the tables)
from backend.integrations import scheduler as integration_scheduler

# Ensure SQLite path is available
for _folder in (paths.DATA_DIR, paths.NOTES_DIR, paths.BACKUP_DIR):
    os.makedirs(_folder, exist_ok=True)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + paths.DB_PATH
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["DEMO_MODE"] = os.environ.get("DEMO_MODE", "false").lower() == "true"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["APP_NAME"] = os.environ.get("APP_NAME", "PrivateGlue")
print(f"DEMO_MODE is set to: {app.config['DEMO_MODE']}")
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    raise RuntimeError(
        "SECRET_KEY environment variable is required. "
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
    )
app.secret_key = _secret_key
app.permanent_session_lifetime = timedelta(hours=1)
force_https = os.environ.get("FORCE_HTTPS", "false").lower() == "true"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=force_https,
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SAMESITE="Lax",
    REMEMBER_COOKIE_SECURE=force_https,
)
app.config["RATELIMIT_STORAGE_URI"] = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

# Behind a reverse proxy every request seems to come from the proxy, so the login rate limit
# would count all visitors as one. TRUSTED_PROXIES is the number of proxies in front of the
# app (usually 1). Only then are X-Forwarded-For/-Proto/-Host believed. Leave it at 0 when
# the app is reached directly, otherwise anyone could fake their address.
try:
    _trusted_proxies = max(0, int(os.environ.get("TRUSTED_PROXIES", "0")))
except ValueError:
    _trusted_proxies = 0
if _trusted_proxies:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=_trusted_proxies, x_proto=_trusted_proxies,
                            x_host=_trusted_proxies)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"



init_security(app, login_manager, force_https=force_https)


db.init_app(app)
csrf.init_app(app)
limiter.init_app(app)

# Gunicorn starts several workers at once, and each one imports this module. Without a lock
# they race to create the database: one creates an empty app.db, another sees the file and
# tries to upgrade tables that don't exist yet, and the container crashes on first start.
# An exclusive file lock makes the workers initialise the database one at a time.
import fcntl

with open(os.path.join(paths.DATA_DIR, ".init.lock"), "w") as _init_lock:
    fcntl.flock(_init_lock, fcntl.LOCK_EX)
    try:
        with app.app_context():
            features.discover()  # imports the features, so their tables are known
            check_and_upgrade_database()
            upgrade_feature_columns()
            db.create_all()
            initialize_default_users()
    finally:
        fcntl.flock(_init_lock, fcntl.LOCK_UN)

app_setup.setup(app)

@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200

# Automatic integration syncs. Does nothing until an admin turns an integration on.
integration_scheduler.start(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
