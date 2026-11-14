"""Shared "create or update a device" logic for every integration that imports devices."""
from datetime import datetime

from backend.extensions import db
from backend.integrations.models import ExternalLink
from backend.models.devices import Device

DEVICE_FIELDS = (
    "hostname", "ip_address", "mac_address", "device_type", "operating_system",
    "os_version", "serial_number", "location",
)
# Lengths of the Device columns: imported values are cut to fit.
_MAX_LEN = {
    "hostname": 255, "ip_address": 45, "mac_address": 45, "device_type": 100,
    "operating_system": 100, "os_version": 50, "serial_number": 100, "location": 100,
}


def normalize_mac(value):
    """Return a MAC as lowercase aa:bb:cc:dd:ee:ff, or None when it is not a MAC."""
    if not value:
        return None
    hexdigits = "".join(c for c in str(value).lower() if c in "0123456789abcdef")
    if len(hexdigits) != 12:
        return None
    return ":".join(hexdigits[i:i + 2] for i in range(0, 12, 2))


def _clean(fields):
    out = {}
    for name in DEVICE_FIELDS:
        value = fields.get(name)
        if value is None:
            continue
        value = str(value).strip()
        if name == "mac_address":
            value = normalize_mac(value) or ""
        if name == "ip_address":
            value = value.split("/")[0]  # drop a prefix length such as 10.0.0.5/24
        if value:
            out[name] = value[:_MAX_LEN[name]]
    return out


def _find_existing(integration, external_id, fields):
    link = ExternalLink.query.filter_by(
        integration=integration, object_type="device", external_id=str(external_id)
    ).first()
    if link:
        device = db.session.get(Device, link.local_id)
        if device:
            return device, link
        db.session.delete(link)  # the device was deleted locally: forget the stale link
        db.session.flush()

    # Not linked yet: adopt a device somebody already entered by hand, most reliable key first.
    serial = fields.get("serial_number")
    if serial:
        device = Device.query.filter(db.func.lower(Device.serial_number) == serial.lower()).first()
        if device:
            return device, None
    mac = fields.get("mac_address")
    if mac:
        for device in Device.query.filter(Device.mac_address.isnot(None)).all():
            if normalize_mac(device.mac_address) == mac:
                return device, None
    hostname = fields.get("hostname")
    if hostname:
        device = Device.query.filter(db.func.lower(Device.hostname) == hostname.lower()).first()
        if device:
            return device, None
    return None, None


def upsert_device(integration, external_id, fields, external_url=None, overwrite=False):
    """Create or update one device from another system.

    integration: the integration key, e.g. "netbox".
    external_id: the record's stable id in that system.
    fields: dict with any of DEVICE_FIELDS. ``hostname`` is required for a new device.
    overwrite: False (default) only fills in fields that are empty locally, so manual edits
               in PrivateGlue are never lost. True makes the other system the source of truth.

    Returns (device, action) where action is "created", "updated" or "unchanged".
    Does not commit: the caller commits once at the end of the sync.
    """
    fields = _clean(fields)
    device, link = _find_existing(integration, external_id, fields)
    action = "unchanged"

    if device is None:
        if not fields.get("hostname"):
            raise ValueError("a new device needs a hostname")
        device = Device(**fields)
        db.session.add(device)
        db.session.flush()  # get device.id for the link
        action = "created"
    else:
        for name, value in fields.items():
            current = getattr(device, name)
            if current == value:
                continue
            if overwrite or not current:
                setattr(device, name, value)
                action = "updated"

    if link is None:
        link = ExternalLink(integration=integration, object_type="device",
                            external_id=str(external_id), local_id=device.id)
        db.session.add(link)
    link.local_id = device.id
    link.external_url = (external_url or None) and external_url[:500]
    link.last_seen = datetime.utcnow()
    return device, action


def links_for_device(device_id):
    """External links of one device, for showing "Synced from ..." on the device page."""
    return ExternalLink.query.filter_by(object_type="device", local_id=device_id).all()
