"""Database tables used by the integrations framework. All new tables: db.create_all()
adds them to existing installs, no change to existing tables."""
import json
from datetime import datetime

from backend.extensions import db
from backend.utils.encryption import fernet


class IntegrationConfig(db.Model):
    """Saved settings and state of one integration."""
    __tablename__ = "integration_config"

    key = db.Column(db.String(50), primary_key=True)
    enabled = db.Column(db.Boolean, default=False, nullable=False)
    interval_minutes = db.Column(db.Integer, default=0, nullable=False)  # 0 = manual only
    settings_json = db.Column(db.Text, default="{}", nullable=False)
    _secrets = db.Column("secrets", db.LargeBinary, nullable=True)  # Fernet-encrypted JSON
    running_since = db.Column(db.DateTime, nullable=True)
    last_run_at = db.Column(db.DateTime, nullable=True)
    last_status = db.Column(db.String(20), nullable=True)  # ok, warning, error
    last_message = db.Column(db.Text, nullable=True)

    @property
    def settings(self):
        try:
            return json.loads(self.settings_json or "{}")
        except ValueError:
            return {}

    @settings.setter
    def settings(self, value):
        self.settings_json = json.dumps(value or {})

    @property
    def secrets(self):
        if not self._secrets:
            return {}
        try:
            return json.loads(fernet.decrypt(self._secrets).decode())
        except Exception:
            # Wrong or lost encryption key: behave as "no secrets saved" so the admin can
            # re-enter them instead of the page crashing.
            return {}

    @secrets.setter
    def secrets(self, value):
        self._secrets = fernet.encrypt(json.dumps(value or {}).encode()) if value else None


class IntegrationRun(db.Model):
    """One line of history per sync run."""
    __tablename__ = "integration_run"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), index=True, nullable=False)
    trigger = db.Column(db.String(20), default="manual")  # manual, schedule, cli
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default="running")  # running, ok, warning, error
    summary = db.Column(db.Text, nullable=True)
    details = db.Column(db.Text, nullable=True)  # error lines, one per line


class ExternalLink(db.Model):
    """Remembers which record in another system a local record came from.

    Lets a sync find "its" device again after a rename, without adding columns to Device.
    """
    __tablename__ = "integration_external_link"
    __table_args__ = (
        db.UniqueConstraint("integration", "object_type", "external_id", name="uq_external_link"),
    )

    id = db.Column(db.Integer, primary_key=True)
    integration = db.Column(db.String(50), nullable=False)
    object_type = db.Column(db.String(30), nullable=False)  # "device"
    external_id = db.Column(db.String(255), nullable=False)
    local_id = db.Column(db.Integer, index=True, nullable=False)
    external_url = db.Column(db.String(500), nullable=True)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
