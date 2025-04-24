import os
from backend.models.users import User
from backend.extensions import db
from werkzeug.security import generate_password_hash

def initialize_default_users():
    if User.query.count() > 0:
        return

    created = []

    admin_user = os.getenv("PG_ADMIN_USERNAME")
    admin_pass = os.getenv("PG_ADMIN_PASSWORD")
    demo_user = os.getenv("PG_DEMO_USERNAME")
    demo_pass = os.getenv("PG_DEMO_PASSWORD")

    if admin_user and admin_pass:
        user = User(username=admin_user, password_hash=generate_password_hash(admin_pass), role="admin")
        db.session.add(user)
        created.append(admin_user)

    if demo_user and demo_pass:
        user = User(username=demo_user, password_hash=generate_password_hash(demo_pass), role="editor")
        db.session.add(user)
        created.append(demo_user)

    if created:
        db.session.commit()
        print(f"[INIT] Created default user(s): {', '.join(created)}")
