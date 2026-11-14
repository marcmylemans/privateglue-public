"""Background thread that runs automatic syncs.

Every gunicorn worker starts one. That is safe: run_sync() claims the integration in the
database first, so only one worker actually runs a given sync.
Turn it off with the environment variable INTEGRATIONS_SCHEDULER=off.
"""
import os
import threading
import time

from backend.extensions import db
from backend.integrations import runner

CHECK_EVERY_SECONDS = 60
_started = False


def tick(app):
    """One scheduler pass. Separate from the loop so tests can call it."""
    with app.app_context():
        try:
            for key in runner.due_keys():
                runner.run_sync(key, trigger="schedule")
        finally:
            db.session.remove()


def start(app):
    global _started
    if _started or os.environ.get("INTEGRATIONS_SCHEDULER", "on").lower() in ("off", "false", "0"):
        return False
    _started = True

    def loop():
        time.sleep(15)  # let the app finish starting
        while True:
            try:
                tick(app)
            except Exception as exc:
                print(f"[integrations] scheduler error: {exc}")
            time.sleep(CHECK_EVERY_SECONDS)

    threading.Thread(target=loop, name="integration-scheduler", daemon=True).start()
    return True
