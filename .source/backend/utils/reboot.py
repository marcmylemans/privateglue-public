"""Restart the app from inside, used after a backup has been restored.

A restore replaces the database file and the encryption key on disk. Every worker still has
the old database open and the old key in memory, so stored passwords would be unreadable and
the restored accounts invisible until the workers start again.

Under gunicorn (the Docker image and the Proxmox install both use it) a worker can ask the
gunicorn master to do exactly that: on SIGHUP it starts fresh workers and lets the old ones
finish their request. The process manager (Docker, systemd) never notices, and requests
that arrive in between simply wait for the new workers.
"""
import os
import signal
import threading


def can_restart():
    """True when this process is a gunicorn worker, so its parent is the gunicorn master."""
    return os.environ.get("SERVER_SOFTWARE", "").startswith("gunicorn") and os.getppid() > 0


def _reload_workers(master_pid):
    try:
        os.kill(master_pid, signal.SIGHUP)
    except OSError as exc:  # the master is gone or belongs to another user
        print(f"[ERROR] Could not restart the app after the restore: {exc}")


def restart_app(delay=1.0):
    """Restart all workers shortly after the current request has been answered.
    Returns False when that is not possible here (for example the development server);
    the caller then has to tell the user to restart by hand."""
    if not can_restart():
        return False
    timer = threading.Timer(delay, _reload_workers, args=(os.getppid(),))
    timer.daemon = True
    timer.start()
    return True
