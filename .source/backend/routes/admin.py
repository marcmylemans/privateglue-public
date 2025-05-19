from flask import Blueprint, send_file, flash, redirect, url_for, send_from_directory, request, render_template, current_app
from flask_login import login_required
from backend.utils.rbac import admin_required
from backend.models.users import User
from backend.models.devices import Device
from backend.models.credentials import Credential
from backend.extensions import db
import os, sys
import zipfile
import socket
import platform
from datetime import datetime
import secrets
import subprocess

admin_bp = Blueprint("admin", __name__)

def get_git_version():
    try:
        version = subprocess.check_output(['git', 'describe', '--tags', '--always'], cwd=os.path.dirname(__file__), stderr=subprocess.DEVNULL).decode().strip()
        return version
    except Exception:
        return None

def get_app_version():
    # Prefer container version from environment, fallback to git version
    version = os.environ.get("APP_VERSION")
    if version:
        return version
    return get_git_version() or "unknown"

@admin_bp.route("/admin/backup")
@login_required
@admin_required
def create_backup():
    db_path = "/app/data/app.db"
    secret_path = "/app/secret/secret.key"
    notes_dir = "/app/notes"
    backup_dir = "/app/backups"

    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    zip_filename = f"backup-{timestamp}.zip"
    zip_path = os.path.join(backup_dir, zip_filename)

    with zipfile.ZipFile(zip_path, "w") as zipf:
        if os.path.exists(db_path):
            zipf.write(db_path, arcname="app.db")
        if os.path.exists(secret_path):
            zipf.write(secret_path, arcname="secret.key")
        if os.path.isdir(notes_dir):
            for filename in os.listdir(notes_dir):
                filepath = os.path.join(notes_dir, filename)
                if os.path.isfile(filepath) and (filename.endswith(".md") or (filename.endswith(".meta.json"))):
                    arcname = os.path.join("notes", filename)
                    zipf.write(filepath, arcname=arcname)

    # Flash message with download link
    flash(
        f"Backup created successfully: <a href='{url_for('admin.download_backup', filename=zip_filename)}' class='alert-link'>Download backup</a>",
        "success"
    )
    return redirect(url_for("index"))


@admin_bp.route("/admin/restore", methods=["POST"])
def restore_backup():
    backup_folder = "/app/backups"
    backup_files = [f for f in os.listdir(backup_folder) if f.endswith(".zip")]

    if not backup_files:
        flash("No backup file found to restore.", "danger")
        return redirect(url_for("setup.first_run"))

    backup_path = os.path.join(backup_folder, backup_files[0])  # Use the first .zip file found
    with zipfile.ZipFile(backup_path, 'r') as zip_ref:
        zip_ref.extractall("/app")  # Extract into root of app where /data, /notes, /secret exist

    flash("Backup successfully restored. Restarting app to apply changes...", "info")
    os.execv(sys.executable, ['python'] + sys.argv)

@admin_bp.route("/admin/download/<filename>")
@login_required
@admin_required
def download_backup(filename):
    backup_dir = "/app/backups"
    return send_from_directory(backup_dir, filename, as_attachment=True)    

@admin_bp.route("/admin/users")
@login_required
@admin_required
def list_users():
    users = User.query.all()
    return render_template("admin/users.html", users=users)

@admin_bp.route("/admin/users/edit/<int:user_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == "POST":
        # Update role
        new_role = request.form.get("role")
        if new_role in ["admin", "editor", "readonly"]:
            user.role = new_role

        # Update password (optional)
        new_password = request.form.get("new_password", "").strip()
        if new_password:
            user.set_password(new_password)

        # Force password reset flag
        user.force_password_reset = bool(request.form.get("force_password_reset"))

        db.session.commit()
        flash("User updated successfully.", "success")
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

    db.session.delete(user)
    db.session.commit()
    flash(f"User '{user.username}' has been deleted.", "success")
    return redirect(url_for("admin.list_users"))

@admin_bp.route("/admin/users/reset/<int:user_id>", methods=["GET", "POST"])
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
            flash(f"Password for '{user.username}' has been reset.", "success")
            return redirect(url_for("admin.list_users"))

    return render_template("admin/reset_password.html", user=user)

@admin_bp.route("/admin/users/create", methods=["GET", "POST"])
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
        elif User.query.filter_by(username=username).first():
            flash("Username already exists.", "danger")
        else:
            user = User(username=username, role=role)
            user.set_password(password)
            user.force_password_reset = True  # User must reset password on first login
            db.session.add(user)
            db.session.commit()
            flash(f"User '{username}' created successfully.", "success")
            return redirect(url_for("admin.list_users"))

    return render_template("admin/create_user.html")

@admin_bp.route("/admin/about")
@login_required
@admin_required
def about_page():

    user_count = User.query.count()
    device_count = Device.query.count()
    note_count = len([f for f in os.listdir("/app/notes") if f.endswith(".md")])
    credential_count = Credential.query.count()

    from backend.routes.devices import get_or_create_probe_api_key
    api_key = get_or_create_probe_api_key()
    version = get_app_version()

    system_info = {
        "App Version": version,
        "App Mode": "Demo" if current_app.config.get("DEMO_MODE") else "Production",
        "Users": user_count,
        "Devices": device_count,
        "Notes": note_count,
        "Credentials": credential_count,
        "Hostname": socket.gethostname(),
        "Python": platform.python_version(),
        "Platform": platform.system(),
        "Current Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "API Key for Probe": api_key,
    }

    return render_template("admin/about.html", system_info=system_info)
