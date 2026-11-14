import os
import tempfile
import time

from cryptography.fernet import Fernet
from backend.utils import paths

# Check for environment variable, fallback to default
SECRET_KEY_PATH = paths.secret_key_path()


def load_or_create_secret_file(path, generate, mode=0o600):
    """Return the contents of `path`, creating it with `generate()` if it doesn't exist.

    Safe when several processes start at once (gunicorn workers). The old
    check-then-write approach let every worker generate its own key; the last
    write won on disk while the other workers kept encrypting with a key that was
    never saved, so their credentials became unreadable after a restart.

    Here each process writes a complete file under a temporary name and then
    hard-links it into place. link() fails if the target exists, so exactly one
    process wins and everyone else reads the winner's file, never a partial one.
    """
    if os.path.exists(path):
        return _read_nonempty(path)

    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    value = generate()
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(value)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.chmod(tmp_path, mode)
        try:
            os.link(tmp_path, path)
            # Return exactly what other processes will read back from the file.
            return value.strip()
        except FileExistsError:
            return _read_nonempty(path)
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass


def _read_nonempty(path, attempts=50):
    # A file written by an older version could in theory be caught mid-write; retry briefly.
    for _ in range(attempts):
        with open(path, "rb") as f:
            data = f.read().strip()
        if data:
            return data
        time.sleep(0.1)
    raise RuntimeError(f"{path} exists but is empty")


def generate_key():
    return Fernet.generate_key()


def load_key():
    return load_or_create_secret_file(SECRET_KEY_PATH, generate_key)


# Fernet instance
fernet = Fernet(load_key())
