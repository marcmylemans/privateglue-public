from backend.extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default="readonly")
    force_password_reset = db.Column(db.Boolean, default=False)
    # Raised whenever the password or role changes. It is part of the login session id, so
    # every session opened before the change stops working (a stolen session cookie dies
    # when the password is changed).
    session_version = db.Column(db.Integer, default=0, nullable=False, server_default="0")

    def get_id(self):
        return f"{self.id}.{self.session_version or 0}"

    def invalidate_sessions(self):
        self.session_version = (self.session_version or 0) + 1


    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        self.invalidate_sessions()

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == "admin"

    def is_editor(self):
        return self.role in ["admin", "editor"]
