"""Activity log: who opened, copied and changed what.

The routes report events through ``backend.utils.audit.record``; this feature stores them
in its own table and shows them to admins, on /admin/activity and in an Activity panel on
each credential. Rows are never edited. They stay when the user or the item is deleted:
that is the point of a log. When an item is deleted its rows are marked ``detached``, so
an id that SQLite hands out again later never inherits the old item's history.
"""
from datetime import datetime, timedelta, timezone

from backend.extensions import db
from backend.features import Feature
from backend.features.audit import wording

LABEL_MAX = 255
DETAIL_MAX = 500
DEDUPE_SECONDS = 60
KEEP_DAYS = 365

# Failures are never folded together: ten failed sign-ins in a minute must show as ten.
NEVER_DEDUPE = frozenset({"auth.sign_in_failed", "auth.two_factor_failed"})

# Targets that can disappear, and the events that say they did.
_DELETABLE = ("credential", "device", "note", "user")

# Day (UTC) of the last clean-up in this worker. Two workers may both clean up on the same
# day; deleting rows that are already gone is harmless.
_last_cleanup = None


class AuditEvent(db.Model):
    __tablename__ = "audit_event"
    __table_args__ = (
        db.Index("ix_audit_event_target", "target_type", "target_id", "at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    at = db.Column(db.DateTime, nullable=False, index=True)          # UTC, without zone
    username = db.Column(db.String(80), index=True)
    action = db.Column(db.String(64), nullable=False, index=True)
    target_type = db.Column(db.String(32))
    target_id = db.Column(db.String(255))
    label = db.Column(db.String(LABEL_MAX))
    detail = db.Column(db.String(DETAIL_MAX))
    ip = db.Column(db.String(45))
    detached = db.Column(db.Boolean, nullable=False, default=False, server_default="0")

    @property
    def sentence(self):
        return wording.sentence(self.action)

    @property
    def panel_phrase(self):
        return wording.panel_phrase(self.action)

    @property
    def tone(self):
        return wording.tone(self.action)


def _utc_naive(value):
    if value is None:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _cut(value, size):
    if value is None:
        return None
    value = str(value).strip()
    return value[:size] or None


def _cleanup(now):
    global _last_cleanup
    today = now.date()
    if _last_cleanup == today:
        return
    _last_cleanup = today
    AuditEvent.query.filter(AuditEvent.at < now - timedelta(days=KEEP_DAYS)).delete(
        synchronize_session=False)


def _is_repeat(row):
    if row.action in NEVER_DEDUPE:
        return False
    since = row.at - timedelta(seconds=DEDUPE_SECONDS)
    query = AuditEvent.query.filter(
        AuditEvent.username.is_(None) if row.username is None else AuditEvent.username == row.username,
        AuditEvent.action == row.action,
        AuditEvent.target_type.is_(None) if row.target_type is None else AuditEvent.target_type == row.target_type,
        AuditEvent.target_id.is_(None) if row.target_id is None else AuditEvent.target_id == row.target_id,
        AuditEvent.detail.is_(None) if row.detail is None else AuditEvent.detail == row.detail,
        AuditEvent.at >= since,
        AuditEvent.detached.is_(False),
    )
    return db.session.query(query.exists()).scalar()


def store(event):
    """Write one event and commit. Never raises: a log must not break what it logs."""
    try:
        row = AuditEvent(
            at=_utc_naive(event.get("at")),
            username=_cut(event.get("username"), 80),
            action=_cut(event.get("action"), 64) or "unknown",
            target_type=_cut(event.get("target_type"), 32),
            target_id=_cut(event.get("target_id"), 255),
            label=_cut(event.get("label"), LABEL_MAX),
            detail=_cut(event.get("detail"), DETAIL_MAX),
            ip=_cut(event.get("ip"), 45),
        )
        if row.target_type in _DELETABLE and row.action == f"{row.target_type}.deleted":
            row.detached = True
        if _is_repeat(row):
            return None
        db.session.add(row)
        _cleanup(_utc_naive(None))
        db.session.commit()
        return row
    except Exception as exc:
        try:
            db.session.rollback()
        except Exception:
            pass
        print(f"[audit] could not store an event: {type(exc).__name__}")
        return None


def detach(target_type, target_id):
    """The item is being deleted (caller's transaction, no commit)."""
    if target_id is None:
        return
    AuditEvent.query.filter_by(target_type=target_type, target_id=str(target_id), detached=False) \
        .update({"detached": True}, synchronize_session=False)


class Audit(Feature):
    key = "audit"
    name = "Activity log"
    order = 90

    def init_app(self, app):
        from backend.features.audit.routes import audit_bp
        if audit_bp.name not in app.blueprints:
            app.register_blueprint(audit_bp)

    # --- storing ---------------------------------------------------------------------
    def audit_record(self, event):
        store(event)

    # --- deletes: the rows stay, they just stop belonging to a live item --------------
    def credential_deleted(self, credential):
        detach("credential", getattr(credential, "id", None))

    def device_deleted(self, device):
        detach("device", getattr(device, "id", None))

    def note_deleted(self, filename):
        detach("note", filename)

    def user_deleted(self, user):
        detach("user", getattr(user, "id", None))

    # --- for templates -----------------------------------------------------------------
    def for_credential(self, credential, limit=10):
        return (AuditEvent.query
                .filter_by(target_type="credential", target_id=str(credential.id), detached=False)
                .order_by(AuditEvent.at.desc(), AuditEvent.id.desc())
                .limit(limit).all())

    def ago(self, when):
        from backend.features.audit.routes import ago
        return ago(when)

    def exact(self, when):
        from backend.features.audit.routes import exact
        return exact(when)


FEATURE = Audit()
