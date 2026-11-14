"""Security wiring shared by the real app and the tests: session validation, the forced
password change, the content security policy and the other response headers."""
import secrets

from flask import g, redirect, request, url_for
from flask_login import current_user

from backend.extensions import db

# Endpoints a user may still reach while a password change is required.
FORCE_RESET_ALLOWED = {"auth.force_change_password", "auth.logout", "static", "healthz"}


def load_user(user_id):
    """Flask-Login user loader.

    The session id is "<user id>.<session version>". When the password or role changes the
    version goes up and older sessions no longer match. Plain "<user id>" comes from
    sessions created before this existed and counts as version 0.
    """
    from backend.models.users import User
    raw_id, _, raw_version = str(user_id).partition(".")
    try:
        user = db.session.get(User, int(raw_id))
        version = int(raw_version) if raw_version else 0
    except ValueError:
        return None
    if user is None or (user.session_version or 0) != version:
        return None
    return user


def enforce_password_reset():
    """A user flagged "must change password" can do nothing else until they have."""
    if (current_user.is_authenticated and getattr(current_user, "force_password_reset", False)
            and request.endpoint not in FORCE_RESET_ALLOWED):
        return redirect(url_for("auth.force_change_password"))


def make_csp_nonce():
    # One random value per response. Only <script> blocks carrying it may run, so script
    # injected through a note, a device name or a URL does not execute.
    g.csp_nonce = secrets.token_urlsafe(16)


def content_security_policy(nonce):
    return "; ".join([
        "default-src 'self'",
        f"script-src 'self' 'nonce-{nonce}'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: https:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'self'",
    ])


def init_security(app, login_manager, force_https=False):
    login_manager.user_loader(load_user)
    app.before_request(enforce_password_reset)
    app.before_request(make_csp_nonce)

    @app.context_processor
    def inject_nonce():
        return {"csp_nonce": getattr(g, "csp_nonce", "")}

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault("Content-Security-Policy",
                                    content_security_policy(getattr(g, "csp_nonce", "")))
        # Pages show passwords and inventory: keep them out of shared and disk caches.
        if request.endpoint != "static":
            response.headers.setdefault("Cache-Control", "no-store")
        if force_https:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
