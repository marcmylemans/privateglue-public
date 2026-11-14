"""Where PrivateGlue keeps its files.

Everything lives under one folder, the "home". In the Docker image that is /app, which is
why it is the default and why nothing changes for container installs. A native install
(for example the Proxmox LXC script) sets PRIVATEGLUE_HOME to wherever the app was put.

    <home>/data      database, probe key, discovered devices
    <home>/notes     Markdown notes
    <home>/backups   backups made in the app
    <home>/secret    encryption key for stored credentials
"""
import os

HOME = os.path.abspath(os.environ.get("PRIVATEGLUE_HOME") or "/app")

DATA_DIR = os.path.join(HOME, "data")
NOTES_DIR = os.path.join(HOME, "notes")
BACKUP_DIR = os.path.join(HOME, "backups")
SECRET_DIR = os.path.join(HOME, "secret")

DB_PATH = os.path.join(DATA_DIR, "app.db")


def secret_key_path():
    """Where the encryption key is. SECRET_KEY_PATH can still be set by itself (it existed
    before PRIVATEGLUE_HOME). Read when asked, not when this module loads, so it does not
    matter which module happens to be imported first."""
    return os.environ.get("SECRET_KEY_PATH") or os.path.join(SECRET_DIR, "secret.key")


def read_version():
    """The app version: APP_VERSION when set (the Docker image sets it), otherwise the
    VERSION file that a release archive carries. Empty when neither exists."""
    version = (os.environ.get("APP_VERSION") or "").strip()
    if version:
        return version
    for folder in (HOME, os.path.join(os.path.dirname(__file__), "..", "..")):
        try:
            with open(os.path.join(folder, "VERSION"), encoding="utf-8") as handle:
                return handle.read().strip()[:40]
        except OSError:
            continue
    return ""
