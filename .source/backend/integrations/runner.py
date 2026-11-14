"""Runs an integration's sync and records the outcome."""
import threading
import traceback
from datetime import datetime, timedelta

from sqlalchemy import or_, update

from backend import integrations
from backend.extensions import db
from backend.integrations.base import IntegrationError, SyncResult
from backend.integrations.models import IntegrationConfig, IntegrationRun

# A run that has been "running" for longer than this is treated as crashed (container
# restarted mid-sync) and no longer blocks new runs.
STALE_AFTER = timedelta(hours=1)
KEEP_RUNS = 50  # history lines kept per integration


def get_or_create_config(key):
    row = db.session.get(IntegrationConfig, key)
    if row is None:
        row = IntegrationConfig(key=key, enabled=False, interval_minutes=0, settings_json="{}")
        db.session.add(row)
        db.session.flush()
    return row


def build_config(integration, row):
    """Merge defaults, saved settings and decrypted secrets into the dict modules receive."""
    saved = dict(row.settings) if row else {}
    saved.update(row.secrets if row else {})
    config = {}
    for field in integration.fields:
        value = saved.get(field.name, field.default)
        if field.kind == "checkbox":
            value = bool(value)
        elif field.kind == "number":
            try:
                value = int(value)
            except (TypeError, ValueError):
                value = int(field.default or 0)
        elif value is None:
            value = ""
        config[field.name] = value
    return config


def missing_required(integration, config):
    return [f.label for f in integration.fields if f.required and config.get(f.name) in ("", None)]


def _claimable(row, now=None):
    """True when no sync is running, or the running one is stale."""
    now = now or datetime.utcnow()
    return row.running_since is None or row.running_since < now - STALE_AFTER


def _claim(key):
    """Mark the integration as running. False when another worker already runs it."""
    now = datetime.utcnow()
    result = db.session.execute(
        update(IntegrationConfig)
        .where(IntegrationConfig.key == key)
        .where(or_(IntegrationConfig.running_since.is_(None),
                   IntegrationConfig.running_since < now - STALE_AFTER))
        .values(running_since=now)
    )
    db.session.commit()
    return result.rowcount == 1


def run_sync(key, trigger="manual"):
    """Run one sync now, in this thread. Returns the IntegrationRun, or None when the
    integration is unknown or already running. Never raises: failures end up in the run."""
    integration = integrations.get(key)
    if integration is None or not integration.can_sync:
        return None
    get_or_create_config(key)
    db.session.commit()
    if not _claim(key):
        return None

    run = IntegrationRun(key=key, trigger=trigger, status="running")
    db.session.add(run)
    db.session.commit()
    run_id = run.id

    status, summary, details = "ok", "", ""
    try:
        row = db.session.get(IntegrationConfig, key)
        config = build_config(integration, row)
        missing = missing_required(integration, config)
        if missing:
            raise IntegrationError("Missing settings: " + ", ".join(missing))
        result = integration.sync(config) or SyncResult()
        db.session.commit()
        summary = result.summary()
        if result.errors:
            status = "warning"
            details = "\n".join(str(e) for e in result.errors[:200])
    except IntegrationError as exc:
        db.session.rollback()
        status, summary = "error", str(exc)
    except Exception as exc:  # a bug in a module: record it, keep the app alive
        db.session.rollback()
        status, summary = "error", f"Unexpected error: {type(exc).__name__}: {exc}"
        details = traceback.format_exc(limit=8)

    now = datetime.utcnow()
    run = db.session.get(IntegrationRun, run_id)
    run.finished_at, run.status, run.summary, run.details = now, status, summary, details
    row = db.session.get(IntegrationConfig, key)
    row.running_since = None
    row.last_run_at, row.last_status, row.last_message = now, status, summary
    db.session.commit()

    old = (IntegrationRun.query.filter_by(key=key)
           .order_by(IntegrationRun.id.desc()).offset(KEEP_RUNS).all())
    for stale in old:
        db.session.delete(stale)
    db.session.commit()
    return db.session.get(IntegrationRun, run_id)


def run_sync_in_background(app, key, trigger="manual"):
    """Start a sync in a thread so the web request returns straight away."""
    def work():
        with app.app_context():
            try:
                run_sync(key, trigger)
            finally:
                db.session.remove()
    thread = threading.Thread(target=work, name=f"integration-{key}", daemon=True)
    thread.start()
    return thread


def due_keys(now=None):
    """Keys of enabled integrations whose automatic interval has passed."""
    now = now or datetime.utcnow()
    due = []
    for row in IntegrationConfig.query.filter_by(enabled=True).all():
        if not row.interval_minutes or row.interval_minutes <= 0:
            continue
        integration = integrations.get(row.key)
        if integration is None or not integration.can_sync:
            continue
        if row.last_run_at is None or now - row.last_run_at >= timedelta(minutes=row.interval_minutes):
            due.append(row.key)
    return due
