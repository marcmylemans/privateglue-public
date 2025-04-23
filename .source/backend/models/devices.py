from backend.extensions import db

class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(80), nullable=False)
    ip_address = db.Column(db.String(120))
    device_type = db.Column(db.String(50))
    location = db.Column(db.String(50))
    # notes = db.Column(db.Text)

    def __repr__(self):
        return f"<Device {self.hostname}>"
