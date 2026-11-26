"""Pages of two-factor sign-in: the code step at sign-in, the set-up in the profile and the
two admin actions (the policy and a reset for a lost phone)."""
from flask import (Blueprint, current_app, flash, redirect, render_template, request,
                   session, url_for)
from flask_login import current_user, login_required, login_user

from backend.extensions import db, limiter
from backend.models.users import User
from backend.utils import audit
from backend.utils.rbac import admin_required, readonly_required

from . import service

bp = Blueprint("two_factor", __name__)

# Pages a signed-in user can still open while the policy asks them to set it up.
POLICY_ALLOWED = {"two_factor.setup", "auth.logout", "auth.force_change_password", "static", "healthz"}


def _remain_signed_in(user):
    """After a change that signs out the user's other sessions: keep this one, the way
    change_password does."""
    user.invalidate_sessions()
    db.session.commit()
    login_user(user, remember=session.permanent)


def _user_key():
    return "two-factor-off:" + str(getattr(current_user, "id", "none"))


def _demo_refused():
    if service.is_demo_user(current_user):
        flash("The demo account cannot use two-factor sign-in.", "warning")
        return redirect(url_for("index"))
    return None


# --- the code step at sign-in ---------------------------------------------------------------

def _back_to_login(message, category="warning"):
    flash(message, category)
    return redirect(url_for("auth.login"))


@bp.route("/sign-in/code", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
@limiter.limit("20 per hour", methods=["POST"], key_func=service.pending_user_key)
def verify():
    data = service.pending()
    if data is None:
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        return redirect(url_for("auth.login"))
    if service.pending_expired(data):
        service.end_pending()
        return _back_to_login("That took too long. Sign in again.")
    user, row = service.pending_user_and_account(data)
    if user is None:
        service.end_pending()
        return _back_to_login("Sign in again.")

    recovery = request.values.get("recovery") == "1"
    error = None
    if request.method == "POST":
        kind = service.check_code_or_recovery(row, request.form.get("code", "")[:64])
        if kind:
            next_url = data.get("next") or ""
            remember = bool(data.get("remember"))
            service.end_pending(row)
            db.session.commit()
            if kind == "recovery":
                audit.record("auth.recovery_code_used", "user", user.id, user.username, username=user.username)
                left = service.recovery_codes_left(user.id)
                flash(f"You used a recovery code. {left} left." if left else
                      "You used your last recovery code. Make new ones in your profile.", "warning")
            from backend.routes.auth import finish_sign_in
            return finish_sign_in(user, remember, next_url)

        row.sign_in_failures = (row.sign_in_failures or 0) + 1
        audit.record("auth.two_factor_failed", "user", user.id, user.username, username=user.username)
        if row.sign_in_failures >= service.MAX_FAILURES:
            service.end_pending(row)
            db.session.commit()
            return _back_to_login("Too many wrong codes. Sign in again.", "danger")
        db.session.commit()
        error = ("That recovery code did not work. Check it and try again." if recovery
                 else "That code did not work. Wait for the next one and try again.")

    return render_template("features/two_factor/verify.html", username=user.username,
                           recovery=recovery, error=error)


@bp.route("/sign-in/code/cancel", methods=["POST"])
def cancel():
    data = service.pending()
    if data is not None:
        user, row = service.pending_user_and_account(data)
        service.end_pending(row)
        db.session.commit()
    return redirect(url_for("auth.login"))


# --- set-up in the profile ------------------------------------------------------------------

def _recovery_page(codes, first_time):
    return render_template("features/two_factor/recovery_codes.html", codes=codes, first_time=first_time)


@bp.route("/profile/two-factor/setup", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
@login_required
@readonly_required
def setup():
    refused = _demo_refused()
    if refused:
        return refused
    user = current_user._get_current_object()
    if service.is_enabled(user):
        flash("Two-factor sign-in is already on.", "info")
        return redirect(url_for("auth.profile"))

    row = service.start_setup(user.id)
    error = None
    if request.method == "POST":
        if service.check_code(row, request.form.get("code", "")[:32]):
            row.enabled_at = service._utcnow()
            row.sign_in_nonce = None
            row.sign_in_failures = 0
            codes = service.new_recovery_codes(user.id)
            _remain_signed_in(user)
            audit.record("auth.two_factor_enabled", "user", user.id, user.username)
            flash("Two-factor sign-in is on. Other devices signed in with this account have been signed out.", "success")
            return _recovery_page(codes, first_time=True)
        error = "That code did not work. Check that the time on your phone is right and try the next code."
    db.session.commit()   # keeps the secret of the unfinished set-up, so the QR code stays the same

    secret = service.secret_of(row)
    return render_template("features/two_factor/setup.html",
                           qr=service.qr_svg(service.provisioning_uri(row, user.username)),
                           secret_grouped=service.grouped(secret), error=error,
                           required=service.policy_applies(user))


def _confirm_page(action, error=None):
    return render_template("features/two_factor/confirm.html", action=action, error=error)


@bp.route("/profile/two-factor/recovery-codes", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
@login_required
@readonly_required
def recovery_codes():
    refused = _demo_refused()
    if refused:
        return refused
    user = current_user._get_current_object()
    row = service.enabled_account(user.id)
    if row is None:
        return redirect(url_for("auth.profile"))
    if request.method == "POST":
        kind = service.check_code_or_recovery(row, request.form.get("code", "")[:64])
        if kind:
            codes = service.new_recovery_codes(user.id)
            _remain_signed_in(user)
            audit.record("auth.recovery_codes_replaced", "user", user.id, user.username)
            flash("New recovery codes made. The old ones no longer work. Other devices have been signed out.", "success")
            return _recovery_page(codes, first_time=False)
        db.session.commit()
        audit.record("auth.two_factor_failed", "user", user.id, user.username, detail="New recovery codes.")
        return _confirm_page("codes", "That code did not work. Try the next one.")
    return _confirm_page("codes")


@bp.route("/profile/two-factor/turn-off", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
@limiter.limit("20 per hour", methods=["POST"], key_func=lambda: _user_key())
@login_required
@readonly_required
def turn_off():
    refused = _demo_refused()
    if refused:
        return refused
    user = current_user._get_current_object()
    row = service.enabled_account(user.id)
    if row is None:
        return redirect(url_for("auth.profile"))
    if request.method == "POST":
        # Password first: a wrong password must not use up a good code.
        ok = (user.check_password(request.form.get("password", ""))
              and service.check_code_or_recovery(row, request.form.get("code", "")[:64]))
        if ok:
            service.remove_for_user(user.id)
            _remain_signed_in(user)
            audit.record("auth.two_factor_disabled", "user", user.id, user.username)
            flash("Two-factor sign-in is off. Other devices signed in with this account have been signed out.", "success")
            return redirect(url_for("auth.profile"))
        db.session.commit()
        audit.record("auth.two_factor_failed", "user", user.id, user.username, detail="Turning off.")
        return _confirm_page("off", "The password or the code is not right.")
    return _confirm_page("off")


# --- administration -------------------------------------------------------------------------

@bp.route("/admin/two-factor/policy", methods=["POST"])
@login_required
@admin_required
def save_policy():
    if current_app.config.get("DEMO_MODE"):
        flash("The two-factor setting cannot be changed in demo mode.", "warning")
        return redirect(url_for("admin.list_users"))
    value = request.form.get("policy", "")
    if value not in service.POLICIES:
        flash("Choose who must use two-factor sign-in.", "danger")
        return redirect(url_for("admin.list_users"))
    before = service.policy()
    service.set_policy(value)
    db.session.commit()
    if value != before:
        audit.record("settings.two_factor_policy_changed",
                     detail=f"Two-factor sign-in required for: {service.POLICY_LABELS[value].lower()}.")
    flash("Saved." if value == "nobody" else
          "Saved. People it applies to are asked to set it up on their next page.", "success")
    return redirect(url_for("admin.list_users"))


@bp.route("/admin/users/<int:user_id>/two-factor/reset", methods=["POST"])
@login_required
@admin_required
def reset(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        return redirect(url_for("admin.list_users"))
    if user.id == current_user.id:
        flash("To turn off your own two-factor sign-in, use your profile.", "warning")
        return redirect(url_for("auth.profile"))
    if not service.is_enabled(user):
        flash(f"'{user.username}' does not use two-factor sign-in.", "info")
        return redirect(url_for("admin.edit_user", user_id=user.id))
    service.remove_for_user(user.id)
    user.invalidate_sessions()
    db.session.commit()
    audit.record("auth.two_factor_reset", "user", user.id, user.username)
    flash(f"Two-factor sign-in reset for '{user.username}'. They sign in with their password and can set it up again.", "success")
    return redirect(url_for("admin.list_users"))


# --- the policy, on every page --------------------------------------------------------------

def enforce_policy():
    """When the policy applies to a signed-in user who has not set it up, every page leads
    to the set-up until they have. Runs after the forced password change, which comes first."""
    if request.endpoint in POLICY_ALLOWED or not current_user.is_authenticated:
        return None
    if getattr(current_user, "force_password_reset", False):
        return None
    if not service.policy_applies(current_user) or service.is_enabled(current_user):
        return None
    return redirect(url_for("two_factor.setup"))
