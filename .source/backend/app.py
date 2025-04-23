import os, json
from flask import Flask, render_template, request, session, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from datetime import timedelta
from backend.models.users import User
from backend.extensions import db
from backend.models.devices import Device
from backend.models.credentials import Credential
from backend.routes.devices import devices_bp
from backend.routes.notes import notes_bp
from backend.routes.auth import auth_bp
from backend.routes.admin import admin_bp
from backend.routes.credentials import credentials_bp

# Ensure SQLite path is available
os.makedirs("/app/data", exist_ok=True)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////app/data/app.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["DEMO_MODE"] = os.getenv("DEMO_MODE", "false").lower() == "true"
app.secret_key = os.environ.get("SECRET_KEY", "changeme")
app.permanent_session_lifetime = timedelta(hours=1)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"



@login_manager.user_loader
def load_user(user_id):
    from backend.models.users import User
    return db.session.get(User, int(user_id))



db.init_app(app)

with app.app_context():
    db.create_all()

app.register_blueprint(devices_bp)
app.register_blueprint(notes_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(credentials_bp)
app.register_blueprint(admin_bp)

NOTES_DIR = "/app/notes"

@app.context_processor
def inject_user_role():
    from flask_login import current_user
    return dict(user_role=getattr(current_user, 'role', None))

@app.route("/")
@login_required
def index():
    # Count devices
    device_count = Device.query.count()

    # Count notes
    note_files = [f for f in os.listdir(NOTES_DIR) if f.endswith(".md")]
    note_count = len(note_files)

    # Count credentials
    credential_count = Credential.query.count()

    # Load last 5 notes sorted by modification time
    note_paths = sorted(
        note_files,
        key=lambda f: os.path.getmtime(os.path.join(NOTES_DIR, f)),
        reverse=True
    )[:5]

    recent_notes = []
    for filename in note_paths:
        base = filename[:-3]
        meta_path = os.path.join(NOTES_DIR, base + ".meta.json")
        device = None
        if os.path.exists(meta_path):
            with open(meta_path, "r") as f:
                meta = json.load(f)
                if meta.get("device_id"):
                    device = Device.query.get(meta["device_id"])
        recent_notes.append({
            "filename": filename,
            "device": device
        })

    recent_devices = Device.query.order_by(Device.id.desc()).limit(3).all()
    recent_credentials = Credential.query.order_by(Credential.id.desc()).limit(3).all()

    return render_template(
        "dashboard.html",
        device_count=device_count,
        note_count=note_count,
        credential_count=credential_count,
        recent_devices=recent_devices,
        recent_credentials=recent_credentials,
        recent_notes=recent_notes
    )

@app.route("/search")
@login_required
def search():
    query = request.args.get("q", "").lower()
    device_results = []
    note_results = []

    if query:
        # Search devices
        device_results = Device.query.filter(
            db.or_(
                Device.hostname.ilike(f"%{query}%"),
                Device.ip_address.ilike(f"%{query}%")
            )
        ).all()

        # Search notes (by filename)
        note_files = [f for f in os.listdir(NOTES_DIR) if f.endswith(".md")]
        for f in note_files:
            if query in f.lower():
                note_results.append(f)

    return render_template(
        "search.html",
        query=query,
        devices=device_results,
        notes=note_results
    )

@app.route("/flash")
def flash_helper():
    msg = request.args.get("msg", "Done")
    cat = request.args.get("cat", "info")
    flash(msg, cat)
    return "", 204


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000)
