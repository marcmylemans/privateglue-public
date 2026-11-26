import os
import zipfile
import shutil
from backend.utils import paths

ALLOWED_BACKUP_MEMBERS = ("app.db", "secret.key")

def _is_safe_member(target_dir, member_name):
    member_path = os.path.realpath(os.path.join(target_dir, member_name))
    target_root = os.path.realpath(target_dir)
    return os.path.commonpath([target_root, member_path]) == target_root

def _is_allowed_member(member_name):
    if member_name in ALLOWED_BACKUP_MEMBERS:
        return True
    if member_name.startswith("files/"):
        # Files that features keep next to the database (attachments, for example).
        return True
    return member_name.startswith("notes/") and (
        member_name.endswith(".md") or member_name.endswith(".meta.json")
    )


def write_backup_zip(zip_path):
    """Write a complete backup: the database, the encryption key, the notes and whatever
    files the features keep."""
    from backend import features

    db_path = paths.DB_PATH
    secret_path = paths.secret_key_path()
    notes_dir = paths.NOTES_DIR

    with zipfile.ZipFile(zip_path, "w") as zipf:
        if os.path.exists(db_path):
            zipf.write(db_path, arcname="app.db")
        if os.path.exists(secret_path):
            zipf.write(secret_path, arcname="secret.key")
        if os.path.isdir(notes_dir):
            for filename in os.listdir(notes_dir):
                filepath = os.path.join(notes_dir, filename)
                if os.path.isfile(filepath) and (filename.endswith(".md") or (filename.endswith(".meta.json"))):
                    zipf.write(filepath, arcname=os.path.join("notes", filename))
        for feature in features.all_features():
            prefix = f"files/{feature.key}/"
            for filepath, arcname in feature.backup_files() or []:
                arcname = arcname.replace(os.sep, "/")
                if arcname.startswith(prefix) and ".." not in arcname.split("/") and os.path.isfile(filepath):
                    zipf.write(filepath, arcname=arcname)
    return zip_path

def extract_backup_zip(zip_path, extract_to=None):
    extract_to = extract_to or paths.HOME
    temp_dir = os.path.join(extract_to, "temp_restore")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.namelist():
                if member.endswith("/"):
                    continue
                if not _is_safe_member(temp_dir, member):
                    raise ValueError(f"Unsafe archive path: {member}")
                if not _is_allowed_member(member):
                    raise ValueError(f"Unexpected backup member: {member}")
            zip_ref.extractall(temp_dir)

        # Move files into place
        if os.path.exists(os.path.join(temp_dir, "app.db")):
            os.makedirs(os.path.join(extract_to, "data"), exist_ok=True)
            shutil.move(os.path.join(temp_dir, "app.db"), os.path.join(extract_to, "data", "app.db"))

        if os.path.exists(os.path.join(temp_dir, "secret.key")):
            os.makedirs(os.path.join(extract_to, "secret"), exist_ok=True)
            shutil.move(os.path.join(temp_dir, "secret.key"), os.path.join(extract_to, "secret", "secret.key"))

        notes_dir = os.path.join(temp_dir, "notes")
        if os.path.isdir(notes_dir):
            os.makedirs(os.path.join(extract_to, "notes"), exist_ok=True)
            for filename in os.listdir(notes_dir):
                shutil.move(os.path.join(notes_dir, filename), os.path.join(extract_to, "notes", filename))

        # Files that features keep: put the restored set in place of the current one.
        files_dir = os.path.join(temp_dir, "files")
        if os.path.isdir(files_dir):
            os.makedirs(os.path.join(extract_to, "data"), exist_ok=True)
            target = os.path.join(extract_to, "data", "files")
            if os.path.isdir(target):
                shutil.rmtree(target)
            shutil.move(files_dir, target)

        # Clean up
        shutil.rmtree(temp_dir)

        return True, "Backup restored successfully."

    except Exception as e:
        print(f"[ERROR] Backup restore failed: {e}")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        return False, str(e)
