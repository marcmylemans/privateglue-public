"""Two-factor sign-in for PrivateGlue itself: after the password, a six-digit code from an
authenticator app (TOTP), with recovery codes for when the phone is gone.

* ``models.py``: the tables (per-user secret and recovery code hashes, the policy row).
* ``service.py``: the logic, without pages.
* ``routes.py``: the code step at sign-in, the set-up in the profile, the admin actions.

The sign-in route (``backend/routes/auth.py``) calls ``service.begin_sign_in`` after a
correct password. It imports this package directly, not through the feature registry, so a
broken package stops the app instead of silently letting people in without their code.
"""
from backend.features import Feature

from . import service
from .models import TwoFactorAccount, TwoFactorRecoveryCode, TwoFactorSetting  # noqa: F401  (registers the tables)
from .routes import bp, enforce_policy


class TwoFactor(Feature):
    key = "two_factor"
    name = "Two-factor sign-in"
    order = 80
    blueprint = bp

    def init_app(self, app):
        # Registered after the app's own checks, so the forced password change comes first.
        app.before_request(enforce_policy)

    def user_deleted(self, user):
        if user is not None and user.id is not None:
            service.remove_for_user(user.id)

    # --- for templates (feat.two_factor....) ----------------------------------------------
    def status(self, user):
        """What the profile panel shows: {"on", "since", "codes_left", "required"}."""
        row = service.enabled_account(user.id)
        return {
            "on": row is not None,
            "since": row.enabled_at if row is not None else None,
            "codes_left": service.recovery_codes_left(user.id) if row is not None else 0,
            "required": service.policy_applies(user),
        }

    def enabled_user_ids(self):
        return service.enabled_user_ids()

    def is_enabled(self, user):
        return service.is_enabled(user)

    def policy(self):
        return service.policy()

    def policy_applies(self, user, current=None):
        return service.policy_applies(user, current)

    def policy_choices(self):
        return [("nobody", "Nobody", "Each person chooses for themselves."),
                ("admins", "Administrators", "Every admin account must use it."),
                ("everyone", "Everyone", "Every account must use it.")]


FEATURE = TwoFactor()
