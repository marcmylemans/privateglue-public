"""Password age: when a password was last changed, an optional renewal reminder, and the
last five previous passwords.

Times are stored as naive UTC (SQLite keeps no time zone) and compared in UTC. Credentials
that existed before this feature have no row: their age is unknown, nothing nags about them,
and tracking starts at their next password change.
"""
from datetime import datetime, timedelta, timezone

from flask import has_request_context, request

from backend.extensions import db
from backend.features import Feature
from backend.models.credentials import Credential
from backend.utils.encryption import fernet

KEEP = 5
FIELD = "password_age_remind"
#: (days, label). 0 means no reminder.
CHOICES = [(0, "Never"), (90, "Every 90 days"), (180, "Every 180 days"), (365, "Every year")]
_ALLOWED = {days for days, _ in CHOICES}


class PasswordAge(db.Model):
    __tablename__ = "password_age"
    id = db.Column(db.Integer, primary_key=True)
    credential_id = db.Column(db.Integer, db.ForeignKey("credential.id"), unique=True, index=True, nullable=False)
    changed_at = db.Column(db.DateTime, nullable=True)  # UTC; None means unknown
    remind_days = db.Column(db.Integer, nullable=True)  # None means no reminder


class PasswordHistory(db.Model):
    __tablename__ = "password_history"
    id = db.Column(db.Integer, primary_key=True)
    credential_id = db.Column(db.Integer, db.ForeignKey("credential.id"), index=True, nullable=False)
    _password = db.Column("password", db.LargeBinary, nullable=False)  # encrypted with fernet
    replaced_at = db.Column(db.DateTime, nullable=False)  # UTC

    def get_decrypted_password(self):
        try:
            return fernet.decrypt(self._password).decode()
        except Exception:
            return "[Unable to decrypt]"


# --- time helpers ----------------------------------------------------------------------------

def utcnow():
    return datetime.now(timezone.utc)


def as_utc(value):
    """Datetimes from SQLite come back naive; they are UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _store(value):
    """Naive UTC for the database."""
    return as_utc(value).replace(tzinfo=None)


def ago(value, now=None):
    """'today', 'yesterday', '3 days ago', '2 weeks ago', '4 months ago', '2 years ago'."""
    value = as_utc(value)
    if value is None:
        return ""
    now = as_utc(now) if now else utcnow()
    days = max(0, (now - value).days)
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    for unit, size in (("year", 365), ("month", 30), ("week", 7), ("day", 1)):
        if days >= size:
            n = days // size
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    return "today"


def exact(value):
    """Full date for a tooltip, such as '26 Nov 2026, 14:02 UTC'."""
    value = as_utc(value)
    return f"{value.day} {value:%b %Y, %H:%M} UTC" if value else ""


def iso(value):
    value = as_utc(value)
    return value.isoformat(timespec="seconds") if value else ""


def remind_label(days):
    for value, label in CHOICES:
        if value == days:
            return label.lower()
    return f"every {days} days"


def _parse_choice(raw):
    try:
        value = int(str(raw).strip() or 0)
    except (TypeError, ValueError):
        return None
    return value if value in _ALLOWED else None


def due_at(row):
    if row is None or not row.changed_at or not row.remind_days:
        return None
    return as_utc(row.changed_at) + timedelta(days=row.remind_days)


def is_due_row(row, now=None):
    when = due_at(row)
    return when is not None and (now or utcnow()) >= when


class Info:
    """What the credential page shows about one credential."""

    def __init__(self, row, now=None):
        now = now or utcnow()
        self.tracked = row is not None and row.changed_at is not None
        self.changed_at = as_utc(row.changed_at) if self.tracked else None
        self.remind_days = (row.remind_days or 0) if row is not None else 0
        self.due_at = due_at(row)
        self.due = is_due_row(row, now)
        self.changed_ago = ago(self.changed_at, now) if self.tracked else ""
        self.changed_exact = exact(self.changed_at)
        self.changed_iso = iso(self.changed_at)
        self.remind_text = remind_label(self.remind_days) if self.remind_days else ""
        self.due_ago = ago(self.due_at, now) if self.due else ""


class PasswordAgeFeature(Feature):
    key = "password_age"
    name = "Password age"
    order = 40
    # The age line belongs directly under the password, above a one-time code row.
    slot_order = {"credential_view_login_bottom": 15}

    choices = CHOICES
    field = FIELD
    keep = KEEP

    # --- data for templates ------------------------------------------------------------------
    def _rows(self):
        """Every row by credential id, read once per request (the list page asks per row)."""
        cache = getattr(request, "_password_age_rows", None) if has_request_context() else None
        if cache is None:
            cache = {row.credential_id: row for row in PasswordAge.query.all()}
            if has_request_context():
                request._password_age_rows = cache
        return cache

    def row(self, credential):
        return PasswordAge.query.filter_by(credential_id=credential.id).first()

    def info(self, credential):
        return Info(self.row(credential))

    def remind_days(self, credential):
        if credential is None or not getattr(credential, "id", None):
            return 0
        row = self.row(credential)
        return (row.remind_days or 0) if row else 0

    def is_due(self, credential):
        return is_due_row(self._rows().get(credential.id))

    def due_ids(self, now=None):
        now = now or utcnow()
        rows = PasswordAge.query.filter(PasswordAge.changed_at.isnot(None), PasswordAge.remind_days > 0).all()
        return [row.credential_id for row in rows if is_due_row(row, now)]

    def due_credentials(self):
        """Due credentials, most overdue first: a list of (credential, 'due ... ago' text)."""
        now = utcnow()
        rows = PasswordAge.query.filter(PasswordAge.changed_at.isnot(None), PasswordAge.remind_days > 0).all()
        due = sorted((r for r in rows if is_due_row(r, now)), key=lambda r: (due_at(r), r.credential_id))
        if not due:
            return []
        creds = {c.id: c for c in Credential.query.filter(Credential.id.in_([r.credential_id for r in due]))}
        return [(creds[r.credential_id], ago(due_at(r), now)) for r in due if r.credential_id in creds]

    def history(self, credential):
        """Previous passwords, newest first, decrypted for the credential page only."""
        now = utcnow()
        entries = (PasswordHistory.query.filter_by(credential_id=credential.id)
                   .order_by(PasswordHistory.replaced_at.desc(), PasswordHistory.id.desc())
                   .limit(KEEP).all())
        return [{"id": e.id, "password": e.get_decrypted_password(), "ago": ago(e.replaced_at, now),
                 "exact": exact(e.replaced_at), "iso": iso(e.replaced_at)} for e in entries]

    def history_count(self, credential):
        return min(KEEP, PasswordHistory.query.filter_by(credential_id=credential.id).count())

    # --- hooks -------------------------------------------------------------------------------
    def credential_validate(self, form, credential):
        if FIELD in form and _parse_choice(form.get(FIELD)) is None:
            return ["Choose how often to be reminded from the list."]
        return []

    def credential_saved(self, credential, form, created, password_changed, old_password):
        now = _store(utcnow())
        row = PasswordAge.query.filter_by(credential_id=credential.id).first()

        def ensure():
            nonlocal row
            if row is None:
                row = PasswordAge(credential_id=credential.id)
                db.session.add(row)
            return row

        if created:
            ensure().changed_at = now
        elif password_changed:
            if old_password:
                db.session.add(PasswordHistory(credential_id=credential.id, replaced_at=now,
                                               _password=fernet.encrypt(old_password.encode())))
                db.session.flush()
                self._prune(credential.id)
            ensure().changed_at = now

        if FIELD in form:
            choice = _parse_choice(form.get(FIELD))
            if choice is not None and (choice or row is not None):
                ensure().remind_days = choice or None

    def _prune(self, credential_id):
        old = (PasswordHistory.query.filter_by(credential_id=credential_id)
               .order_by(PasswordHistory.replaced_at.desc(), PasswordHistory.id.desc())
               .offset(KEEP).all())
        for entry in old:
            db.session.delete(entry)

    def credential_deleted(self, credential):
        PasswordHistory.query.filter_by(credential_id=credential.id).delete()
        PasswordAge.query.filter_by(credential_id=credential.id).delete()

    def credential_query(self, query, args):
        if args.get("due") == "1":
            return query.filter(Credential.id.in_(self.due_ids()))
        return query


FEATURE = PasswordAgeFeature()
