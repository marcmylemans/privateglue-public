"""The logic of two-factor sign-in, kept apart from the pages so it is easy to test.

Nothing here commits unless the function says so.
"""
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone

from flask import current_app, session
from flask_login import current_user, logout_user
from markupsafe import Markup

from backend.extensions import db
from backend.utils import totp
from backend.utils.encryption import fernet
from backend.utils.security import is_safe_redirect_target

from .models import TwoFactorAccount, TwoFactorRecoveryCode, TwoFactorSetting

POLICIES = ("nobody", "admins", "everyone")
POLICY_LABELS = {"nobody": "Nobody", "admins": "Administrators", "everyone": "Everyone"}

PENDING_KEY = "two_factor_pending"
PENDING_SECONDS = 5 * 60          # the code step must be done within this time
MAX_FAILURES = 5                  # wrong codes before the sign-in starts over
SETUP_SECONDS = 60 * 60           # an unfinished set-up keeps its secret this long

RECOVERY_CODE_COUNT = 10
# No 0/o, 1/l/i: easy to read back from paper. 31 symbols, 12 of them: about 59 bits.
RECOVERY_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
RECOVERY_LENGTH = 12

DEMO_USERNAME = "demo"


def _now():
    """Seconds since 1970. One place, so tests can move the clock."""
    return time.time()


def _utcnow():
    return datetime.fromtimestamp(_now(), timezone.utc).replace(tzinfo=None)


# --- accounts and policy -----------------------------------------------------------------

def account(user_id):
    return db.session.get(TwoFactorAccount, user_id)


def enabled_account(user_id):
    row = account(user_id)
    return row if row is not None and row.enabled_at is not None else None


def is_enabled(user):
    return user is not None and enabled_account(user.id) is not None


def enabled_user_ids():
    rows = db.session.query(TwoFactorAccount.user_id).filter(TwoFactorAccount.enabled_at.isnot(None))
    return {r[0] for r in rows}


def is_demo_user(user):
    return getattr(user, "username", None) == DEMO_USERNAME


def policy():
    row = db.session.get(TwoFactorSetting, 1)
    return row.policy if row is not None and row.policy in POLICIES else "nobody"


def set_policy(value):
    if value not in POLICIES:
        raise ValueError("Unknown policy.")
    row = db.session.get(TwoFactorSetting, 1)
    if row is None:
        row = TwoFactorSetting(id=1)
        db.session.add(row)
    row.policy = value


def policy_applies(user, current=None):
    """Must this user have two-factor sign-in? The demo account never: it cannot turn it on."""
    if user is None or is_demo_user(user):
        return False
    current = current or policy()
    return current == "everyone" or (current == "admins" and getattr(user, "role", None) == "admin")


def remove_for_user(user_id):
    """Delete every two-factor row of a user (turning off, admin reset, user deleted)."""
    TwoFactorRecoveryCode.query.filter_by(user_id=user_id).delete()
    TwoFactorAccount.query.filter_by(user_id=user_id).delete()


# --- secrets ------------------------------------------------------------------------------

def _encrypt(secret):
    return fernet.encrypt(secret.encode("ascii"))


def secret_of(row):
    return fernet.decrypt(row.secret).decode("ascii")


def start_setup(user_id):
    """The unfinished set-up of a user, made when there is none (or it is old). Returns the row."""
    row = account(user_id)
    if row is not None and row.enabled_at is not None:
        return row
    now = _utcnow()
    if row is not None and (now - row.created_at).total_seconds() < SETUP_SECONDS:
        return row
    if row is None:
        row = TwoFactorAccount(user_id=user_id)
        db.session.add(row)
    row.secret = _encrypt(totp.random_secret())
    row.created_at = now
    row.last_step = None
    row.sign_in_nonce = None
    row.sign_in_failures = 0
    return row


def grouped(secret):
    """"JBSWY3DPEHPK3PXP" as "JBSW Y3DP EHPK 3PXP", easier to type by hand."""
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))


def provisioning_uri(row, username):
    issuer = current_app.config.get("APP_NAME") or "PrivateGlue"
    return totp.provisioning_uri(secret_of(row), username, issuer)


def qr_svg(text):
    """The QR code as inline SVG markup, or None when it cannot be made (the page then
    only shows the secret as text). Inline markup, not a data: address in an attribute,
    so the secret is never in an HTML attribute."""
    try:
        import segno
        svg = segno.make(text, error="m").svg_inline(scale=1, border=4, omitsize=True,
                                                      svgclass="tf-qr-svg", lineclass="tf-qr-line")
    except Exception as exc:  # no segno, or anything else: the text secret is enough
        print(f"[two_factor] QR code not made: {type(exc).__name__}")
        return None
    svg = svg.replace("<svg ", '<svg role="img" aria-label="QR code for your authenticator app" ', 1)
    return Markup(svg)


# --- codes --------------------------------------------------------------------------------

def check_code(row, candidate):
    """Is ``candidate`` the current six-digit code (one step either way for clock drift),
    and newer than the last code used? Marks its time step as used. No commit."""
    step = totp.verify(secret_of(row), candidate, at=_now())
    if step is None:
        return False
    if row.last_step is not None and step <= row.last_step:
        return False
    row.last_step = step
    return True


def _normalize_recovery(text):
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


def _hash_recovery(code, salt=None):
    # A recovery code is 12 random symbols (about 59 bits). Guessing that from a hash is
    # out of reach even with a fast hash, so a salted SHA-256 is enough, and it keeps the
    # check of ten codes at every attempt cheap. The salt makes equal codes hash apart.
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.sha256(salt + code.encode("ascii")).hexdigest()
    return f"sha256${salt.hex()}${digest}"


def _matches(stored, code):
    try:
        method, salt_hex, digest = stored.split("$")
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    if method != "sha256":
        return False
    return hmac.compare_digest(_hash_recovery(code, salt), stored)


def new_recovery_codes(user_id):
    """Replace a user's recovery codes. Returns the new codes in plain text, to show once."""
    TwoFactorRecoveryCode.query.filter_by(user_id=user_id).delete()
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(RECOVERY_LENGTH))
        db.session.add(TwoFactorRecoveryCode(user_id=user_id, code_hash=_hash_recovery(raw)))
        codes.append("-".join(raw[i:i + 4] for i in range(0, RECOVERY_LENGTH, 4)))
    return codes


def use_recovery_code(user_id, text):
    """Is ``text`` one of the user's recovery codes? Removes it when it is. No commit."""
    code = _normalize_recovery(text)
    if len(code) != RECOVERY_LENGTH:
        return False
    found = None
    for row in TwoFactorRecoveryCode.query.filter_by(user_id=user_id).all():
        if _matches(row.code_hash, code) and found is None:
            found = row
    if found is None:
        return False
    db.session.delete(found)
    return True


def recovery_codes_left(user_id):
    return TwoFactorRecoveryCode.query.filter_by(user_id=user_id).count()


def looks_like_totp(text):
    cleaned = "".join((text or "").split())
    return len(cleaned) == 6 and cleaned.isdigit()


def check_code_or_recovery(row, text):
    """A six-digit code or a recovery code. Returns "code", "recovery" or None. No commit."""
    if looks_like_totp(text):
        return "code" if check_code(row, text) else None
    return "recovery" if use_recovery_code(row.user_id, text) else None


# --- the sign-in waiting for its code -----------------------------------------------------

def begin_sign_in(user, remember, next_url):
    """After a correct password. When the user has two-factor sign-in on, remember the
    sign-in in the session (nothing that signs anyone in) and return True; else False.
    Commits."""
    row = enabled_account(user.id)
    if row is None:
        session.pop(PENDING_KEY, None)
        return False
    if current_user.is_authenticated:   # someone else signed in on this browser: not any more
        logout_user()
    nonce = secrets.token_urlsafe(24)
    row.sign_in_nonce = nonce
    row.sign_in_failures = 0
    db.session.commit()
    session[PENDING_KEY] = {
        "uid": user.id,
        "ver": user.session_version or 0,
        "remember": bool(remember),
        "next": next_url if is_safe_redirect_target(next_url) else "",
        "started": int(_now()),
        "nonce": nonce,
    }
    return True


def pending():
    """The waiting sign-in from the session as a dict, or None. Does not check the database."""
    data = session.get(PENDING_KEY)
    if not isinstance(data, dict):
        return None
    return data


def pending_expired(data):
    started = data.get("started")
    if not isinstance(started, int):
        return True
    age = _now() - started
    return age < -5 or age > PENDING_SECONDS


def pending_user_and_account(data):
    """The user and the account of a waiting sign-in that is still valid, else (None, None).
    Valid: same password and role as at the password step (session version), two-factor
    still on, and the database still expects this very sign-in."""
    from backend.models.users import User
    try:
        user = db.session.get(User, int(data.get("uid")))
    except (TypeError, ValueError):
        return None, None
    if user is None or (user.session_version or 0) != data.get("ver"):
        return None, None
    row = enabled_account(user.id)
    nonce = data.get("nonce")
    if (row is None or not row.sign_in_nonce or not isinstance(nonce, str)
            or not hmac.compare_digest(row.sign_in_nonce, nonce)):
        return None, None
    return user, row


def end_pending(row=None):
    """Forget the waiting sign-in, in the session and (when given) in the database. No commit."""
    session.pop(PENDING_KEY, None)
    if row is not None:
        row.sign_in_nonce = None
        row.sign_in_failures = 0


def pending_user_key():
    """Rate-limit key: the user of the waiting sign-in."""
    data = pending() or {}
    return "two-factor-user:" + str(data.get("uid", "none"))
