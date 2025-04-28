from backend.extensions import db

class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(255), nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    device_type = db.Column(db.String(100), nullable=True)
    operating_system = db.Column(db.String(100))
    os_version = db.Column(db.String(50))
    serial_number = db.Column(db.String(100))
    license_key = db.Column(db.String(255))
    location = db.Column(db.String(100))

    # notes = db.Column(db.Text)

    def __repr__(self):
        return f"<Device {self.hostname}>"
