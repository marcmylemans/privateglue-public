import os
import zipfile
import shutil

ALLOWED_BACKUP_MEMBERS = ("app.db", "secret.key")

def _is_safe_member(target_dir, member_name):
    member_path = os.path.realpath(os.path.join(target_dir, member_name))
    target_root = os.path.realpath(target_dir)
    return os.path.commonpath([target_root, member_path]) == target_root

def _is_allowed_member(member_name):
    if member_name in ALLOWED_BACKUP_MEMBERS:
        return True
    return member_name.startswith("notes/") and (
        member_name.endswith(".md") or member_name.endswith(".meta.json")
    )

def extract_backup_zip(zip_path, extract_to="/app"):
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

        # Clean up
        shutil.rmtree(temp_dir)

        return True, "Backup restored successfully."

    except Exception as e:
        print(f"[ERROR] Backup restore failed: {e}")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        return False, str(e)
