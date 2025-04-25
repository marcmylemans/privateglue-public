# backend/utils/db_upgrade.py

import sqlite3
import os
from backend.extensions import db

def check_and_upgrade_database():
    db_path = "/app/data/app.db"  # or wherever your db lives

    if db.engine.url.drivername.startswith("sqlite"):
        if not os.path.exists(db_path):
            print("Database file does not exist. Skipping upgrade.")
            return

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if the column already exists
        cursor.execute("PRAGMA table_info(user);")
        columns = [row[1] for row in cursor.fetchall()]

        if "force_password_reset" not in columns:
            print("Adding force_password_reset column to User table...")
            cursor.execute("ALTER TABLE user ADD COLUMN force_password_reset BOOLEAN DEFAULT 0;")
            conn.commit()
            print("Database upgraded successfully.")
        else:
            print("Database already up-to-date.")

        conn.close()
    else:
        print("Non-SQLite database detected. No auto-upgrade performed.")
