"""Storage for the network probe: its API key and the devices it last reported.

Both live as files in the data folder, so every gunicorn worker sees the same key and the
same list, and both survive a restart. (They used to be kept in memory per worker: a probe
result landed in one worker and the page was served by another, so the list came and went.)
"""
import json
import os
import secrets
import tempfile
import time

from backend.utils import paths
from backend.utils.encryption import load_or_create_secret_file

DATA_DIR = paths.DATA_DIR
KEY_FILE = "probe_api_key.txt"
DISCOVERED_FILE = "discovered_devices.json"
MAX_DEVICES = 5000


def _path(name):
    return os.path.join(DATA_DIR, name)


def _write_atomic(path, data, mode=0o600):
    """Write a whole file under a temporary name, then swap it in, so no reader ever sees
    half a file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --- API key ---------------------------------------------------------------

def get_api_key():
    """The current key, created on first use. Read from disk every time so that a key
    replaced in one worker is the key in all of them."""
    return load_or_create_secret_file(
        _path(KEY_FILE), lambda: secrets.token_urlsafe(32).encode()
    ).decode().strip()


def rotate_api_key():
    """Replace the key. Probes using the old key stop working at once."""
    key = secrets.token_urlsafe(32)
    _write_atomic(_path(KEY_FILE), key.encode())
    return key


# --- discovered devices ----------------------------------------------------

def save_discovered(devices):
    """Replace the stored list. Returns the batch id of the new list."""
    batch = f"{int(time.time())}-{secrets.token_hex(4)}"
    payload = {"batch": batch, "received_at": int(time.time()), "devices": list(devices)[:MAX_DEVICES]}
    _write_atomic(_path(DISCOVERED_FILE), json.dumps(payload).encode())
    return batch


def load_discovered():
    """Return (devices, batch, received_at). Empty when nothing is stored or the file is damaged."""
    try:
        with open(_path(DISCOVERED_FILE), "rb") as handle:
            payload = json.loads(handle.read().decode())
        devices = [d for d in payload.get("devices", []) if isinstance(d, dict)]
        return devices, str(payload.get("batch", "")), int(payload.get("received_at", 0))
    except (OSError, ValueError, AttributeError, TypeError):
        return [], "", 0


def clear_discovered():
    try:
        os.unlink(_path(DISCOVERED_FILE))
    except OSError:
        pass
