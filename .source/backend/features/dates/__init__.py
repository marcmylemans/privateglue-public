"""Dates to watch: warranty, support, licence and certificate end dates on a device.

People record the dates on the device form. The device page lists them with how long is
left, and the dashboard lists what has run out or runs out within ``WARN_DAYS``.
"""
import re
from datetime import date

from flask import request

from backend.extensions import db
from backend.features import Feature

KINDS = [
    ("warranty", "Warranty", "shield-check"),
    ("support", "Support contract", "headset"),
    ("licence", "Licence", "patch-check"),
    ("certificate", "Certificate", "file-earmark-lock"),
    ("other", "Other", "calendar-event"),
]
KIND_KEYS = [k for k, _, _ in KINDS]
_KIND_LABELS = {k: label for k, label, _ in KINDS}
_KIND_ICONS = {k: icon for k, _, icon in KINDS}

MAX_PER_DEVICE = 12
LABEL_MAX = 120
NOTE_MAX = 200
WARN_DAYS = 60
DASHBOARD_LIMIT = 5

_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"]
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DeviceDate(db.Model):
    __tablename__ = "device_date"
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("device.id"), index=True, nullable=False)
    kind = db.Column(db.String(20), nullable=False, default="other")
    label = db.Column(db.String(LABEL_MAX))
    due_on = db.Column(db.Date, nullable=False)
    note = db.Column(db.String(NOTE_MAX))


# --- plain helpers (tested on their own) ---------------------------------------------------

def parse_date(text):
    """A date from the date input, which always sends YYYY-MM-DD. Anything else is None."""
    text = (text or "").strip()
    if not _ISO_DATE.match(text):
        return None
    try:
        value = date.fromisoformat(text)
    except ValueError:
        return None
    if not 1900 <= value.year <= 2199:
        return None
    return value


def long_date(value):
    """14 March 2027, the same in every locale."""
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"


def _plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _span(days):
    """A distance in days as people say it: 3 weeks, 8 months, 2 years."""
    if days < 14:
        return _plural(days, "day")
    if days < 60:
        return _plural(days // 7, "week")
    if days < 335:
        return _plural(max(2, round(days / 30.44)), "month")
    return _plural(max(1, round(days / 365.25)), "year")


def status(due_on, today=None):
    """(text, tone) for a date: tone is "danger" (gone), "warning" (within WARN_DAYS) or
    "quiet". Within the warning window the exact number of days is shown."""
    today = today or date.today()
    days = (due_on - today).days
    if days < 0:
        if days == -1:
            return "Expired yesterday", "danger"
        return f"Expired {_span(-days)} ago", "danger"
    if days == 0:
        return "Expires today", "warning"
    if days == 1:
        return "Expires tomorrow", "warning"
    if days <= WARN_DAYS:
        return f"In {days} days", "warning"
    return f"In {_span(days)}", "quiet"


def kind_label(kind):
    return _KIND_LABELS.get(kind, "Other")


def kind_icon(kind):
    return _KIND_ICONS.get(kind, "calendar-event")


def _clean(text, limit):
    text = " ".join((text or "").split())
    return text[:limit] or None


def read_rows(form):
    """The rows posted by the form, as dicts. Lists of different lengths are padded, so a
    missing field never crashes. Rows without a date are left out. Each dict has the raw
    date text and the parsed date (None when it cannot be read)."""
    kinds = form.getlist("dates_kind")
    labels = form.getlist("dates_label")
    ons = form.getlist("dates_on")
    notes = form.getlist("dates_note")
    count = max(len(kinds), len(labels), len(ons), len(notes), 0)

    def at(values, i):
        return values[i] if i < len(values) else ""

    rows = []
    for i in range(count):
        raw = (at(ons, i) or "").strip()
        if not raw:
            continue
        kind = (at(kinds, i) or "").strip().lower()
        rows.append({
            "kind": kind if kind in KIND_KEYS else "other",
            "label": _clean(at(labels, i), LABEL_MAX),
            "note": _clean(at(notes, i), NOTE_MAX),
            "raw": raw[:20],
            "due_on": parse_date(raw),
        })
    return rows


class _Entry:
    """What a template needs for one date."""

    def __init__(self, row, today, device=None):
        self.id = row.id
        self.kind = row.kind
        self.kind_label = kind_label(row.kind)
        self.icon = kind_icon(row.kind)
        self.label = row.label
        self.note = row.note
        self.due_on = row.due_on
        self.iso = row.due_on.isoformat()
        self.long = long_date(row.due_on)
        self.status, self.tone = status(row.due_on, today)
        self.device = device

    @property
    def title(self):
        return self.label or self.kind_label


class Dates(Feature):
    key = "dates"
    name = "Dates to watch"
    order = 70

    kinds = KINDS
    max_per_device = MAX_PER_DEVICE
    label_max = LABEL_MAX
    note_max = NOTE_MAX
    warn_days = WARN_DAYS

    # --- for templates -----------------------------------------------------------------
    def for_device(self, device):
        """The dates of a device, soonest first."""
        if device is None or not getattr(device, "id", None):
            return []
        today = date.today()
        rows = (DeviceDate.query.filter_by(device_id=device.id)
                .order_by(DeviceDate.due_on, DeviceDate.id).all())
        return [_Entry(r, today) for r in rows]

    def form_rows(self, device, clone=False):
        """Rows to show in the form. After a refused add the posted rows come back, so
        nothing typed is lost. A duplicate starts without dates."""
        if request.method == "POST" and "dates_present" in request.form:
            return [{"kind": r["kind"], "label": r["label"] or "", "note": r["note"] or "",
                     "on": r["due_on"].isoformat() if r["due_on"] else r["raw"]}
                    for r in read_rows(request.form)][:MAX_PER_DEVICE]
        if clone:
            return []
        return [{"kind": e.kind, "label": e.label or "", "note": e.note or "", "on": e.iso}
                for e in self.for_device(device)]

    def running_out(self, limit=DASHBOARD_LIMIT):
        """(entries, total): dates that are gone or end within WARN_DAYS, most urgent first."""
        from datetime import timedelta
        from backend.models.devices import Device

        today = date.today()
        query = (db.session.query(DeviceDate, Device)
                 .join(Device, Device.id == DeviceDate.device_id)
                 .filter(DeviceDate.due_on <= today + timedelta(days=WARN_DAYS))
                 .order_by(DeviceDate.due_on, DeviceDate.id))
        total = query.count()
        entries = [_Entry(row, today, device) for row, device in query.limit(limit).all()]
        return entries, total

    # --- hooks -------------------------------------------------------------------------
    def device_validate(self, form, device):
        if "dates_present" not in form:
            return []
        rows = read_rows(form)
        problems = []
        if any(r["due_on"] is None for r in rows):
            problems.append("A date to watch cannot be read. Pick it with the calendar, or write it as 2027-03-14.")
        if len(rows) > MAX_PER_DEVICE:
            problems.append(f"A device can have at most {MAX_PER_DEVICE} dates to watch.")
        return problems

    def device_saved(self, device, form, created):
        if "dates_present" not in form:
            return  # posted from somewhere without the section: leave the dates alone
        DeviceDate.query.filter_by(device_id=device.id).delete()
        for row in read_rows(form)[:MAX_PER_DEVICE]:
            if row["due_on"] is None:
                continue
            db.session.add(DeviceDate(device_id=device.id, kind=row["kind"], label=row["label"],
                                      due_on=row["due_on"], note=row["note"]))

    def device_deleted(self, device):
        DeviceDate.query.filter_by(device_id=device.id).delete()


FEATURE = Dates()
