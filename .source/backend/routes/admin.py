from flask import Blueprint, send_file, flash, redirect, url_for, send_from_directory
from flask_login import login_required
from backend.utils.rbac import admin_required
import os, sys
import zipfile
from datetime import datetime

admin_bp = Blueprint("admin", __name__)

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