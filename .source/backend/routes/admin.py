from flask import Blueprint, send_file, flash, redirect, url_for, send_from_directory, request, render_template, current_app
from flask_login import login_required, current_user, login_user
from backend.utils.rbac import admin_required
from backend.models.users import User
from backend.models.devices import Device
from backend.models.credentials import Credential
from backend.extensions import db
from backend.utils.backup import extract_backup_zip, write_backup_zip
from backend.utils import audit
from backend import features
import os, sys
import zipfile
import socket
import platform
from datetime import datetime
import subprocess
from backend.utils import paths

admin_bp = Blueprint("admin", __name__)

def get_git_version():
    try:
        version = subprocess.check_output(['git', 'describe', '--tags', '--always'], cwd=os.path.dirname(__file__), stderr=subprocess.DEVNULL).decode().strip()
        return version
    except Exception:
        return None

def get_app_version():
    # Prefer container version from environment, fallback to git version
    version = paths.read_version()
    if version:
        return version
    return get_git_version() or "unknown"

@admin_bp.route("/admin/backup", methods=["POST"])
@login_required
@admin_required
def create_backup():
    backup_dir = paths.BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    zip_filename = f"backup-{timestamp}.zip"
    write_backup_zip(os.path.join(backup_dir, zip_filename))
    audit.record("backup.created", detail=zip_filename)

    flash(f"Backup {zip_filename} created. Download it from the list below.", "success")
    return redirect(url_for("admin.about_page") + "#backups")


@admin_bp.route("/admin/download/<filename>")
@login_required
@admin_required
def download_backup(filename):
    backup_dir = paths.BACKUP_DIR
    audit.record("backup.downloaded", detail=filename)
    return send_from_directory(backup_dir, filename, as_attachment=True)    

@admin_bp.route("/admin/users")
@login_required
@admin_required
def list_users():
    users = User.query.order_by(User.username).all()
    return render_template("admin/users.html", users=users)

@admin_bp.route("/admin/users/edit/<int:user_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == "POST":
        # Update role
        role_changed = False
        new_role = request.form.get("role")
        if new_role in ["admin", "editor", "readonly"]:
            if user.role == "admin" and new_role != "admin" and User.query.filter_by(role="admin").count() <= 1:
                flash("This is the only admin account. Make someone else an admin first.", "danger")
                return redirect(url_for("admin.edit_user", user_id=user.id))
            if new_role != user.role:
                role_changed = True
                user.role = new_role
                # A role change takes effect at once: the user has to sign in again.
                if user.id != current_user.id:
                    user.invalidate_sessions()

        # Update password (optional)
        new_password = request.form.get("new_password", "").strip()
        if new_password:
            if len(new_password) < 8:
                flash("Password must be at least 8 characters long.", "danger")
                return redirect(url_for("admin.edit_user", user_id=user.id))
            user.set_password(new_password)
            if user.id == current_user.id:
                db.session.commit()
                login_user(user)

        # Force password reset flag
        user.force_password_reset = bool(request.form.get("force_password_reset"))

        db.session.commit()
        audit.record("user.updated", "user", user.id, user.username,
                     detail=("Role is now " + user.role + ". " if role_changed else "")
                     + ("Password was set by an administrator." if new_password else "") or None)
        flash(f"User '{user.username}' updated.", "success")
        return redirect(url_for("admin.list_users"))

    return render_template("admin/edit_user.html", user=user)


@admin_bp.route("/admin/users/delete/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)

    # Prevent deletion of your own account
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("admin.list_users"))

    features.emit("user_deleted", user)
    db.session.delete(user)
    db.session.commit()
    audit.record("user.deleted", "user", user_id, user.username)
    flash(f"User '{user.username}' has been deleted.", "success")
    return redirect(url_for("admin.list_users"))

@admin_bp.route("/admin/users/reset/<int:user_id>", methods=["GET", "POST"])
@login_required
@admin_required
def reset_user_password(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == "POST":
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not new_password or not confirm_password:
            flash("Both password fields are required.", "danger")
        elif new_password != confirm_password:
            flash("Passwords do not match.", "danger")
        elif len(new_password) < 8:
            flash("Password must be at least 8 characters long.", "danger")
        else:
            user.set_password(new_password)
            user.force_password_reset = True
            db.session.commit()
            audit.record("user.password_reset", "user", user.id, user.username)
            flash(f"Password for '{user.username}' has been reset.", "success")
            return redirect(url_for("admin.list_users"))

    return render_template("admin/reset_password.html", user=user)

@admin_bp.route("/admin/users/create", methods=["GET", "POST"])
@login_required
@admin_required
def create_user():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()
        role = request.form.get("role", "readonly")

        if not username or not password or not confirm_password:
            flash("All fields are required.", "danger")
        elif password != confirm_password:
            flash("Passwords do not match.", "danger")
        elif len(password) < 8:
            flash("Password must be at least 8 characters long.", "danger")
        elif role not in ("admin", "editor", "readonly"):
            flash("Unknown role.", "danger")
        elif User.query.filter_by(username=username).first():
            flash("Username already exists.", "danger")
        else:
            user = User(username=username, role=role)
            user.set_password(password)
            user.force_password_reset = True  # User must reset password on first login
            db.session.add(user)
            db.session.commit()
            audit.record("user.created", "user", user.id, user.username, detail="Role " + role + ".")
            flash(f"User '{username}' created successfully.", "success")
            return redirect(url_for("admin.list_users"))

    return render_template("admin/create_user.html")

@admin_bp.route("/admin/about")
@login_required
@admin_required
def about_page():

    user_count = User.query.count()
    device_count = Device.query.count()
    note_count = len([f for f in os.listdir(paths.NOTES_DIR) if f.endswith(".md")])
    credential_count = Credential.query.count()

    version = get_app_version()

    system_info = {
        "App version": "0.6.8-BETA2" if current_app.config.get("DEMO_MODE") else version,
        "Mode": "Demo" if current_app.config.get("DEMO_MODE") else "Production",
        "Hostname": socket.gethostname(),
        "Python": platform.python_version(),
        "Platform": platform.system(),
        "Server time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Probe API key": "Shown and replaced under Devices > Discovered.",
    }
    counts = {"Users": user_count, "Devices": device_count, "Notes": note_count, "Credentials": credential_count}

    backup_dir = paths.BACKUP_DIR
    backups = []
    if os.path.isdir(backup_dir):
        for name in os.listdir(backup_dir):
            if name.endswith(".zip"):
                path = os.path.join(backup_dir, name)
                backups.append({"name": name, "size": os.path.getsize(path), "mtime": os.path.getmtime(path)})
    backups.sort(key=lambda b: b["mtime"], reverse=True)

    return render_template("admin/about.html", system_info=system_info, counts=counts, backups=backups)
