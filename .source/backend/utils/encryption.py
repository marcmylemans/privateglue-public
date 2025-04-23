import os
from cryptography.fernet import Fernet

# Check for environment variable, fallback to default
SECRET_KEY_PATH = os.environ.get("SECRET_KEY_PATH", "/app/secret/secret.key")

def generate_key():
    key = Fernet.generate_key()
    os.makedirs(os.path.dirname(SECRET_KEY_PATH), exist_ok=True)
    with open(SECRET_KEY_PATH, "wb") as key_file:
        key_file.write(key)
    return key

def load_key():
    if not os.path.exists(SECRET_KEY_PATH):
        return generate_key()
    with open(SECRET_KEY_PATH, "rb") as key_file:
        return key_file.read()

# Fernet instance
fernet = Fernet(load_key())
