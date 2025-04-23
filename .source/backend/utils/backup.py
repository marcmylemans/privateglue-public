import os
import zipfile
import shutil

def extract_backup_zip(zip_path, extract_to="/app"):
    temp_dir = os.path.join(extract_to, "temp_restore")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
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

        return True

    except Exception as e:
        print(f"[ERROR] Backup restore failed: {e}")
        return False
