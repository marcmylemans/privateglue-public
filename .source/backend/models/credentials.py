from backend.extensions import db
from backend.utils.encryption import fernet
from cryptography.fernet import InvalidToken

# Association table for many-to-many relationship
device_credential_link = db.Table(
    "device_credential_link",
    db.Column("device_id", db.Integer, db.ForeignKey("device.id")),
    db.Column("credential_id", db.Integer, db.ForeignKey("credential.id"))
)

class Credential(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    username = db.Column(db.String(255), nullable=True)
    _password = db.Column("password", db.LargeBinary, nullable=False)
    notes = db.Column(db.Text, nullable=True)

    # Relationship with devices (many-to-many)
    devices = db.relationship(
        "Device",
        secondary=device_credential_link,
        backref="credentials"
    )

    def __init__(self, title, username, password, notes):
        self.title = title
        self.username = username
        self.password = password
        self.notes = notes

    @property
    def password(self):
        return self._password

    @password.setter
    def password(self, value):
        if isinstance(value, str):
            self._password = fernet.encrypt(value.encode())
        elif isinstance(value, bytes):
            self._password = fernet.encrypt(value)
        else:
            raise ValueError("Password must be a string or bytes")

    def get_decrypted_password(self):
        try:
            return fernet.decrypt(self._password).decode()
        except (InvalidToken, Exception):
            return "[Unable to decrypt]"
