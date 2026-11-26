"""One place to say "this happened", for an activity log.

The routes call ``record()``. By itself that does nothing: a feature that keeps a log
picks the events up through the ``audit_record`` hook. Keeping the calls here means the
routes never need to know whether a log exists.

Never put a secret in an event: no passwords, keys, tokens or one-time codes, not even
partly. Say that a password changed, not what it was.

Action names are "<thing>.<what happened>" in the past tense:

    credential.viewed  credential.created  credential.updated  credential.deleted
    credential.password_copied  credential.password_shown   (sent by the browser)
    device.created  device.updated  device.deleted
    note.created  note.updated  note.deleted
    auth.signed_in  auth.sign_in_failed  auth.signed_out  auth.password_changed
    user.created  user.updated  user.deleted  user.password_reset
    backup.created  backup.downloaded  backup.restored
    integration.settings_saved  integration.sync_started
    settings.server_scan_changed  settings.probe_key_replaced

In a page, a button can report what it did with two attributes, which a log feature's
script may send on click:

    <button data-audit="credential.password_copied" data-audit-target="credential:12">
"""
from datetime import datetime, timezone

from flask import has_request_context, request
from flask_login import current_user

from backend import features


def record(action, target_type=None, target_id=None, label=None, detail=None, username=None):
    """Report an event.

    action       what happened, see the list above
    target_type  "credential", "device", "note", "user", "integration" or None
    target_id    its id (a note uses its file name)
    label        its name for people at the time, kept because the thing may be deleted later
    detail       one short plain sentence with extra context, or None
    username     who did it; defaults to the signed-in user
    """
    event = {
        "action": action,
        "target_type": target_type,
        "target_id": None if target_id is None else str(target_id),
        "label": label,
        "detail": detail,
        "username": username if username is not None else _current_username(),
        "ip": request.remote_addr if has_request_context() else None,
        "at": datetime.now(timezone.utc),
    }
    features.emit("audit_record", event)
    return event


def _current_username():
    if not has_request_context():
        return None
    try:
        if current_user.is_authenticated:
            return current_user.username
    except Exception:
        pass
    return None
