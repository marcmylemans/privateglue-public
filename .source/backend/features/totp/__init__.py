"""One-time codes on a credential.

Many admin logins ask for a six-digit code from an authenticator app. When a team shares
the login, that code lives on one person's phone. This feature keeps the secret next to
the password (encrypted the same way) and shows the current code on the credential page,
so anyone who may see the password can also sign in.

The algorithm lives in ``backend/utils/totp.py``; this package only stores the secret,
adds the pieces to the pages and serves a fresh code to the page's script.
"""
import time

from cryptography.fernet import InvalidToken
from flask import Blueprint, g, has_request_context, jsonify, request
from flask_login import login_required

from backend.extensions import db
from backend.features import Feature
from backend.models.credentials import Credential
from backend.utils import audit, totp
from backend.utils.encryption import fernet
from backend.utils.rbac import editor_required, readonly_required

FIELD = "totp_secret"
REMOVE = "totp_remove"

# What happened to the secret in this request, picked up after the commit (see audit_record).
_DETAIL = {
    "added": ("credential.code_secret_added", "A one-time code secret was added."),
    "replaced": ("credential.code_secret_replaced", "The one-time code secret was replaced."),
    "removed": ("credential.code_secret_removed", "The one-time code secret was removed."),
}


class CredentialTotp(db.Model):
    __tablename__ = "credential_totp"
    id = db.Column(db.Integer, primary_key=True)
    credential_id = db.Column(db.Integer, db.ForeignKey("credential.id"), unique=True, index=True, nullable=False)
    _secret = db.Column("secret", db.LargeBinary, nullable=False)
    digits = db.Column(db.Integer, nullable=False, default=6)
    period = db.Column(db.Integer, nullable=False, default=30)
    algorithm = db.Column(db.String(10), nullable=False, default="SHA1")

    def set_secret(self, secret):
        self._secret = fernet.encrypt(secret.encode())

    def get_secret(self):
        """The Base32 secret, or None when it can no longer be decrypted."""
        try:
            return fernet.decrypt(self._secret).decode()
        except (InvalidToken, ValueError, TypeError):
            return None


def group(code):
    """'123456' -> '123 456', for reading. Copying always uses the code without the space."""
    half = len(code) // 2
    return f"{code[:half]} {code[half:]}"


def current_code(row, now=None):
    """The code that is valid now, or None when the secret cannot be read."""
    secret = row.get_secret()
    if not secret:
        return None
    now = time.time() if now is None else now
    try:
        value = totp.code(secret, at=now, digits=row.digits, period=row.period, algorithm=row.algorithm)
    except (totp.InvalidSecret, KeyError, ValueError):
        return None
    # Milliseconds, not whole seconds: the page refreshes the code right when it rolls over.
    left_ms = int((row.period - (now % row.period)) * 1000) or row.period * 1000
    return {"code": value, "grouped": group(value), "expires_in_ms": left_ms,
            "seconds_left": max(1, -(-left_ms // 1000)), "period": row.period, "digits": row.digits}


def _row(credential_id):
    return CredentialTotp.query.filter_by(credential_id=credential_id).first()


def _pasted(form):
    return (form.get(FIELD) or "").strip()


bp = Blueprint("totp", __name__)


@bp.route("/credentials/<int:id>/code")
@login_required
@readonly_required
def code(id):
    """The current code for the page's script. Never cached, 404 without a secret."""
    db.get_or_404(Credential, id)
    row = _row(id)
    if row is None:
        response = jsonify(error="This credential has no one-time code.")
        response.status_code = 404
    else:
        found = current_code(row)
        if found is None:
            response = jsonify(error="The saved secret cannot be read.")
            response.status_code = 409
        else:
            response = jsonify(code=found["code"], expires_in_ms=found["expires_in_ms"],
                               period=found["period"], digits=found["digits"])
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@bp.route("/credentials/code/test", methods=["POST"])
@login_required
@editor_required
def test_code():
    """The "Test code" button on the form: the code for a pasted secret, so it can be compared
    with the authenticator app before saving. The secret arrives in the POST body, never in a URL."""
    try:
        settings = totp.parse(request.form.get("secret", ""))
    except totp.InvalidSecret as exc:
        # A plain answer, not an error status: a typo is not a failure of the page.
        response = jsonify(ok=False, error=str(exc))
    else:
        value = totp.code(settings["secret"], digits=settings["digits"], period=settings["period"],
                          algorithm=settings["algorithm"])
        response = jsonify(ok=True, code=value, grouped=group(value),
                           seconds_left=totp.seconds_left(period=settings["period"]))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


class OneTimeCodes(Feature):
    key = "totp"
    name = "One-time codes"
    order = 20
    blueprint = bp

    # --- helpers for the templates ---------------------------------------------------------
    def for_credential(self, credential):
        """The stored row, or None. Never the secret itself."""
        if credential is None or not getattr(credential, "id", None):
            return None
        return _row(credential.id)

    def has(self, credential):
        """For the list: one query per page, not one per row."""
        ids = g.get("totp_credential_ids")
        if ids is None:
            ids = {cid for (cid,) in db.session.query(CredentialTotp.credential_id)}
            g.totp_credential_ids = ids
        return credential.id in ids

    def current(self, credential):
        """What the credential page shows: None without a secret, {"unreadable": True} when it
        cannot be decrypted, otherwise the code and how long it is valid."""
        row = self.for_credential(credential)
        if row is None:
            return None
        return current_code(row) or {"unreadable": True}

    # --- hooks -------------------------------------------------------------------------------
    def credential_validate(self, form, credential):
        value = _pasted(form)
        if not value or form.get(REMOVE):
            return []
        try:
            totp.parse(value)
        except totp.InvalidSecret as exc:
            return [f"One-time code secret: {exc}"]
        return []

    def credential_saved(self, credential, form, created, password_changed, old_password):
        row = None if created else _row(credential.id)
        if form.get(REMOVE):
            if row is not None:
                db.session.delete(row)
                self._remember(credential.id, "removed")
            return
        value = _pasted(form)
        if not value:
            return  # empty means: keep what is saved
        settings = totp.parse(value)  # already checked in credential_validate
        if row is None:
            row = CredentialTotp(credential_id=credential.id)
            db.session.add(row)
            change = "added"
        else:
            same = (row.get_secret() == settings["secret"] and row.digits == settings["digits"]
                    and row.period == settings["period"] and row.algorithm == settings["algorithm"])
            if same:
                return
            change = "replaced"
        row.set_secret(settings["secret"])
        row.digits = settings["digits"]
        row.period = settings["period"]
        row.algorithm = settings["algorithm"]
        self._remember(credential.id, change)

    def credential_deleted(self, credential):
        CredentialTotp.query.filter_by(credential_id=credential.id).delete()

    def audit_record(self, event):
        # Hooks run before the commit, so the detail is reported once the route has said
        # "credential.created" or "credential.updated" (that event comes after the commit).
        if event.get("action") not in ("credential.created", "credential.updated"):
            return
        changes = g.get("totp_changes") if _in_request() else None
        if not changes:
            return
        change = changes.pop(event.get("target_id"), None)
        if change:
            action, detail = _DETAIL[change]
            audit.record(action, "credential", event["target_id"], event.get("label"), detail=detail)

    @staticmethod
    def _remember(credential_id, change):
        if _in_request():
            changes = g.setdefault("totp_changes", {})
            changes[str(credential_id)] = change


def _in_request():
    return has_request_context()


FEATURE = OneTimeCodes()
