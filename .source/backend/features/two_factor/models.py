"""Tables of two-factor sign-in. Created by themselves at start-up."""
from backend.extensions import db


class TwoFactorAccount(db.Model):
    """One row per user who has two-factor sign-in on, or is setting it up.

    ``enabled_at`` is empty while the set-up is not finished: the secret is then only kept
    so the QR code stays the same when the set-up page is reloaded, and is not used to
    sign in.
    """
    __tablename__ = "two_factor_account"

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    secret = db.Column(db.LargeBinary, nullable=False)          # Fernet token of the Base32 secret
    created_at = db.Column(db.DateTime, nullable=False)
    enabled_at = db.Column(db.DateTime)
    # The time step of the last code that was accepted. A code of that step or older is
    # refused, so a code that was seen (over a shoulder, in a proxy log) cannot be reused.
    last_step = db.Column(db.Integer)
    # The sign-in waiting for its code. The session holds the same value; a session that
    # does not match (an old copy of the cookie, a sign-in ended after 5 wrong codes) is
    # refused. Counting the wrong codes here, not in the cookie, means replaying an old
    # cookie does not reset the count.
    sign_in_nonce = db.Column(db.String(64))
    sign_in_failures = db.Column(db.Integer, nullable=False, default=0, server_default="0")


class TwoFactorRecoveryCode(db.Model):
    """One-time codes for when the phone is gone. Only a salted hash is kept."""
    __tablename__ = "two_factor_recovery_code"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    code_hash = db.Column(db.String(128), nullable=False)


class TwoFactorSetting(db.Model):
    """One row: who must use two-factor sign-in ("nobody", "admins" or "everyone")."""
    __tablename__ = "two_factor_setting"

    id = db.Column(db.Integer, primary_key=True)
    policy = db.Column(db.String(20), nullable=False, default="nobody")
