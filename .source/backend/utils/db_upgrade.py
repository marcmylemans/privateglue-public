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

         # Existing User table upgrade
         cursor.execute("PRAGMA table_info(user);")
         columns = [row[1] for row in cursor.fetchall()]

         if "force_password_reset" not in columns:
             print("Adding force_password_reset column to User table...")
             cursor.execute(
                 "ALTER TABLE user ADD COLUMN force_password_reset BOOLEAN DEFAULT 0;"
             )
             conn.commit()
             print("User table upgraded successfully.")
         else:
             print("User table already up-to-date.")

         # Upgrade Device table with new columns
         cursor.execute("PRAGMA table_info(device);")
         dev_columns = [row[1] for row in cursor.fetchall()]

         # Columns to add: definition includes SQLite type and defaults
         new_columns = {
             "hostname": "TEXT NOT NULL DEFAULT ''",
             "ip_address": "TEXT",
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
