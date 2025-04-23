from functools import wraps
from flask import flash, redirect, request, url_for
from flask_login import current_user

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("You must be logged in to access this page.", "danger")
                return redirect(url_for("auth.login", next=request.url))

            if current_user.role not in roles:
                flash("You don't have permission to perform this action.", "warning")
                return redirect(request.referrer or url_for("index"))

            return f(*args, **kwargs)
        return wrapped
    return decorator

def admin_required(f):
    return role_required("admin")(f)

def editor_required(f):
    return role_required("admin", "editor")(f)

def readonly_required(f):
    return role_required("admin", "editor", "readonly")(f)