import sqlite3
import os
from backend.extensions import db
from backend.utils import paths

def check_and_upgrade_database(db_path=None):
     db_path = db_path or paths.DB_PATH

     if db.engine.url.drivername.startswith("sqlite"):
         if not os.path.exists(db_path):
             print("Database file does not exist. Skipping upgrade.")
             return

         conn = sqlite3.connect(db_path)
         cursor = conn.cursor()

         # Existing User table upgrade. On a brand-new (empty) database the tables don't
         # exist yet: db.create_all() creates them with every column, so skip the upgrade.
         cursor.execute("PRAGMA table_info(user);")
         columns = [row[1] for row in cursor.fetchall()]

         if not columns:
             print("User table does not exist yet. Skipping upgrade.")
         elif "force_password_reset" not in columns:
             print("Adding force_password_reset column to User table...")
             cursor.execute(
                 "ALTER TABLE user ADD COLUMN force_password_reset BOOLEAN DEFAULT 0;"
             )
             conn.commit()
             print("User table upgraded successfully.")
         else:
             print("User table already up-to-date.")

         if columns and "session_version" not in columns:
             print("Adding session_version column to User table...")
             cursor.execute(
                 "ALTER TABLE user ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0;"
             )
             conn.commit()

         # Upgrade Device table with new columns
         cursor.execute("PRAGMA table_info(device);")
         dev_columns = [row[1] for row in cursor.fetchall()]
         if not dev_columns:
             print("Device table does not exist yet. Skipping upgrade.")
             conn.close()
             return

         # Columns to add: definition includes SQLite type and defaults
         new_columns = {
             "hostname": "TEXT NOT NULL DEFAULT ''",
             "ip_address": "TEXT",
             "mac_address": "TEXT",
             "device_type": "TEXT",
             "operating_system": "TEXT",
             "os_version": "TEXT",
             "serial_number": "TEXT",
             "license_key": "TEXT",
             "location": "TEXT"
         }

         for col, col_def in new_columns.items():
             if col not in dev_columns:
                 print(f"Adding '{col}' column to Device table...")
                 cursor.execute(f"ALTER TABLE device ADD COLUMN {col} {col_def};")
                 conn.commit()
                 print(f"Added '{col}' column successfully.")

         # Verify all new columns exist now
         cursor.execute("PRAGMA table_info(device);")
         updated = [row[1] for row in cursor.fetchall()]
         missing = [c for c in new_columns.keys() if c not in updated]
         if not missing:
             print("Device table upgraded successfully or already up-to-date.")

         conn.close()
     else:
         print("Non-SQLite database detected. No auto-upgrade performed.")


def upgrade_feature_columns(db_path=None):
    """Add the columns that features declared on tables that already exist. On a new
    database there is nothing to do: create_all() makes every table complete."""
    from backend import features

    db_path = db_path or paths.DB_PATH
    if not db.engine.url.drivername.startswith("sqlite") or not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    try:
        def table_columns(table):
            if not table.replace("_", "").isalnum():
                return []
            return [row[1] for row in conn.execute(f'PRAGMA table_info("{table}");').fetchall()]

        added = features.upgrade_columns(conn, table_columns)
        conn.commit()
    finally:
        conn.close()
    for name in added:
        print(f"Added column {name}.")
    return added
