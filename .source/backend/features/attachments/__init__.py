"""Attachments: files kept with a device or a note.

A config export, a warranty PDF, a rack photo or a licence file belongs with the device or
the note it is about. This feature stores such files and shows them in an "Attachments"
panel on the device page and on the note page.

How the files are kept:

* One row per file in ``attachment``: who it belongs to (``owner_type`` "device" or "note",
  ``owner_key`` the device id as text or the note's file name), the original name for
  people, a random stored name, the size, who added it and when (UTC).
* The file itself is ``paths.feature_files_dir("attachments")/<stored name>``. The stored
  name is 32 random hex characters, so the name someone uploaded never reaches the file
  system. That rules out path tricks such as ``../../x``.
* Files are stored as they are, not encrypted, like notes. They are for documents, not
  for secrets.
* Downloads are always sent as a download (``Content-Disposition: attachment``) with
  ``application/octet-stream`` and ``nosniff``, so an uploaded HTML or SVG file can never
  run in the app.
"""
import calendar
import os
import re
import secrets
import unicodedata
from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, flash, redirect, request, send_file, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import RequestEntityTooLarge

from backend.extensions import db
from backend.features import Feature
from backend.models.devices import Device
from backend.utils import audit, paths
from backend.utils.rbac import admin_required, editor_required, readonly_required

KEY = "attachments"
MAX_BYTES = 5 * 1024 * 1024
MAX_FILES = 20
MAX_NAME = 200
OWNER_TYPES = ("device", "note")
FIELD = "attachments_file"
_STORED_NAME = re.compile(r"^[0-9a-f]{32}$")


class Attachment(db.Model):
    __tablename__ = "attachment"
    id = db.Column(db.Integer, primary_key=True)
    owner_type = db.Column(db.String(10), nullable=False)
    owner_key = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(MAX_NAME), nullable=False)
    stored_name = db.Column(db.String(64), nullable=False, unique=True)
    size = db.Column(db.Integer, nullable=False)
    uploaded_by = db.Column(db.String(150))
    uploaded_at = db.Column(db.DateTime, nullable=False)  # UTC, without time zone

    __table_args__ = (db.Index("ix_attachment_owner", "owner_type", "owner_key"),)


# --- file names ----------------------------------------------------------------------------

def clean_name(raw):
    """The name to show and to offer on download. Only the last part of a path is kept,
    control characters (null bytes included) and double quotes go, and it is capped at 200
    characters with the extension kept. Returns "" when nothing usable is left, for
    example for a name made only of dots."""
    name = unicodedata.normalize("NFC", str(raw or ""))
    name = re.split(r"[\\/]", name)[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    name = name.replace('"', "")
    name = re.sub(r"\s+", " ", name).strip()
    if not name.strip("."):
        return ""
    if len(name) > MAX_NAME:
        stem, dot, ext = name.rpartition(".")
        if dot and stem and len(ext) <= 10:
            name = stem[:MAX_NAME - len(ext) - 1].rstrip() + "." + ext
        else:
            name = name[:MAX_NAME]
    return name


def _extension(name):
    _, dot, ext = (name or "").rpartition(".")
    return ext.lower() if dot else ""


_KINDS = [
    ("file-earmark-pdf", "PDF", {"pdf"}),
    ("file-earmark-image", "Image", {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "heic", "heif", "tif", "tiff"}),
    ("file-earmark-text", "Text", {"txt", "log", "md", "conf", "cfg", "ini", "rsc"}),
    ("file-earmark-spreadsheet", "Spreadsheet", {"csv", "xls", "xlsx", "ods", "tsv"}),
    ("file-earmark-word", "Document", {"doc", "docx", "odt", "rtf"}),
    ("file-earmark-slides", "Presentation", {"ppt", "pptx", "odp"}),
    ("file-earmark-zip", "Archive", {"zip", "7z", "rar", "tar", "gz", "tgz", "bz2", "xz"}),
    ("file-earmark-code", "Code", {"json", "xml", "yaml", "yml", "sh", "ps1", "py", "html", "htm", "js", "toml"}),
    ("file-earmark-lock", "Licence or certificate", {"lic", "license", "licence", "pem", "crt", "cer", "der", "p12", "pfx", "key", "pub"}),
    ("file-earmark-binary", "Backup", {"bak", "backup", "bin", "img", "iso", "ova", "vmdk", "qcow2"}),
]


def file_kind(name):
    """(Bootstrap icon, label) for a file name, chosen from the extension."""
    ext = _extension(name)
    for icon, label, extensions in _KINDS:
        if ext in extensions:
            return icon, label
    if ext and len(ext) <= 5 and ext.isalnum():
        return "file-earmark", ext.upper()
    return "file-earmark", "File"


def human_size(size):
    size = int(size or 0)
    if size < 1024:
        return f"{size} bytes" if size != 1 else "1 byte"
    if size < 1024 * 1024:
        return f"{round(size / 1024)} KB"
    return f"{size / (1024 * 1024):.1f} MB"


# --- owners ----------------------------------------------------------------------------------

def _notes():
    # Imported when needed: the notes module keeps its own folder, which tests point elsewhere.
    from backend.routes import notes
    return notes


def resolve_owner(owner_type, owner_key):
    """Check the owner exists. Returns (key, target id, label, url) or None.

    A device is known by its id. A note is known by its file name, normalised with the same
    helpers the note pages use, and its file must exist."""
    if owner_type == "device":
        key = str(owner_key or "")
        if not key.isdigit():
            return None
        device = db.session.get(Device, int(key))
        if device is None:
            return None
        return str(device.id), device.id, device.hostname, url_for("devices.view_device", id=device.id)
    if owner_type == "note":
        notes = _notes()
        try:
            filename = notes.normalize_note_filename(owner_key)
            path = notes.get_note_path(filename)
        except ValueError:
            return None
        if not os.path.isfile(path):
            return None
        return filename, filename, filename[:-3], url_for("notes.view_note", filename=filename)
    return None


def _owner_word(owner_type):
    return "device" if owner_type == "device" else "note"


# --- the feature -----------------------------------------------------------------------------

def _folder():
    return paths.feature_files_dir(KEY)


def _path(stored_name):
    if not _STORED_NAME.match(stored_name or ""):
        return None
    return os.path.join(_folder(), stored_name)


def _remove_file(stored_name):
    """Delete a stored file. A file that is already gone is fine."""
    path = _path(stored_name)
    if not path:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        print(f"[attachments] could not remove a stored file: {type(exc).__name__}")


def _rows(owner_type, owner_key):
    return (Attachment.query.filter_by(owner_type=owner_type, owner_key=str(owner_key))
            .order_by(Attachment.uploaded_at.desc(), Attachment.id.desc()).all())


def _timestamp(moment):
    return calendar.timegm(moment.utctimetuple()) if moment else None


class Attachments(Feature):
    key = KEY
    name = "Attachments"
    order = 60

    max_bytes = MAX_BYTES
    max_files = MAX_FILES

    def panel(self, owner_type, owner_key):
        """What the panel template needs: the files, and whether this user may upload."""
        items = []
        for row in _rows(owner_type, owner_key):
            icon, label = file_kind(row.original_name)
            path = _path(row.stored_name)
            items.append({
                "id": row.id,
                "name": row.original_name,
                "icon": icon,
                "kind": label,
                "size": human_size(row.size),
                "by": row.uploaded_by,
                "at": _timestamp(row.uploaded_at),
                "at_text": row.uploaded_at.strftime("%d %b %Y %H:%M UTC") if row.uploaded_at else "",
                "missing": not (path and os.path.isfile(path)),
            })
        role = getattr(current_user, "role", None)
        return {
            "owner_type": owner_type,
            "owner_key": str(owner_key),
            "items": items,
            "can_upload": role in ("admin", "editor"),
            "can_delete": role == "admin",
            "full": len(items) >= MAX_FILES,
        }

    # --- clean-up ---------------------------------------------------------------------
    def _forget(self, owner_type, owner_key):
        for row in Attachment.query.filter_by(owner_type=owner_type, owner_key=str(owner_key)).all():
            _remove_file(row.stored_name)
            db.session.delete(row)

    def device_deleted(self, device):
        self._forget("device", device.id)

    def note_deleted(self, filename):
        self._forget("note", filename)

    # --- backups ----------------------------------------------------------------------
    def backup_files(self):
        out = []
        for row in Attachment.query.all():
            path = _path(row.stored_name)
            if path and os.path.isfile(path):
                out.append((path, f"files/{KEY}/{row.stored_name}"))
        return out


FEATURE = Attachments()


# --- pages -----------------------------------------------------------------------------------

blueprint = Blueprint("attachments", __name__)
FEATURE.blueprint = blueprint


def _back(owner_url=None):
    return redirect(owner_url or url_for("index"))


@blueprint.route("/attachments/<owner_type>/<path:owner_key>/upload", methods=["POST"])
@login_required
@editor_required
def upload(owner_type, owner_key):
    if owner_type not in OWNER_TYPES:
        abort(404)
    owner = resolve_owner(owner_type, owner_key)
    if owner is None:
        flash(f"That {_owner_word(owner_type)} does not exist.", "danger")
        return _back()
    key, target_id, label, owner_url = owner

    if current_app.config.get("DEMO_MODE"):
        flash("Uploads are turned off in demo mode.", "warning")
        return _back(owner_url)

    upload_file = request.files.get(FIELD)
    if upload_file is None or not upload_file.filename:
        flash("Choose a file to upload.", "warning")
        return _back(owner_url)

    name = clean_name(upload_file.filename)
    if not name:
        flash("That file name cannot be used. Rename the file and try again.", "danger")
        return _back(owner_url)

    if Attachment.query.filter_by(owner_type=owner_type, owner_key=key).count() >= MAX_FILES:
        flash(f"This {_owner_word(owner_type)} already has {MAX_FILES} files. Delete one first.", "warning")
        return _back(owner_url)

    data = upload_file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        flash(_too_big_message(), "danger")
        return _back(owner_url)
    if not data:
        flash(f"'{name}' is empty, so it was not added.", "warning")
        return _back(owner_url)

    stored = secrets.token_hex(16)
    path = _path(stored)
    with open(path, "xb") as handle:
        handle.write(data)
    try:
        db.session.add(Attachment(owner_type=owner_type, owner_key=key, original_name=name, stored_name=stored,
                                  size=len(data), uploaded_by=getattr(current_user, "username", None),
                                  uploaded_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        db.session.commit()
    except Exception:
        db.session.rollback()
        _remove_file(stored)
        raise
    audit.record("attachment.uploaded", owner_type, target_id, label, detail=name)
    flash(f"'{name}' added.", "success")
    return _back(owner_url)


@blueprint.route("/attachments/<int:attachment_id>/download")
@login_required
@readonly_required
def download(attachment_id):
    row = db.session.get(Attachment, attachment_id)
    owner = resolve_owner(row.owner_type, row.owner_key) if row else None
    if row is None or owner is None:
        flash("That file does not exist.", "danger")
        return _back()
    _, target_id, label, owner_url = owner
    path = _path(row.stored_name)
    if not path or not os.path.isfile(path):
        flash(f"'{row.original_name}' is missing from the disk. Restore a backup or delete it.", "warning")
        return _back(owner_url)
    audit.record("attachment.downloaded", row.owner_type, target_id, label, detail=row.original_name)
    response = send_file(path, mimetype="application/octet-stream", as_attachment=True,
                         download_name=clean_name(row.original_name) or "attachment", conditional=False,
                         max_age=0)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@blueprint.route("/attachments/<int:attachment_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete(attachment_id):
    row = db.session.get(Attachment, attachment_id)
    if row is None:
        flash("That file does not exist.", "danger")
        return _back()
    owner = resolve_owner(row.owner_type, row.owner_key)
    name, stored, owner_type, owner_key = row.original_name, row.stored_name, row.owner_type, row.owner_key
    db.session.delete(row)
    db.session.commit()
    _remove_file(stored)
    if owner is not None:
        _, target_id, label, owner_url = owner
        audit.record("attachment.deleted", owner_type, target_id, label, detail=name)
    else:
        owner_url = None
        audit.record("attachment.deleted", owner_type, owner_key, None, detail=name)
    flash(f"'{name}' deleted.", "success")
    return _back(owner_url)


def _too_big_message():
    return f"That file is too large. Files can be up to {MAX_BYTES // (1024 * 1024)} MB."


def _drain_body(limit=64 * 1024 * 1024):
    """Read what the browser is still sending, so it sees our answer instead of a dropped
    connection. Only up to a limit, and only when the size was announced."""
    try:
        length = int(request.environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return
    if not 0 < length <= limit:
        return
    stream = request.environ.get("wsgi.input")
    if stream is None:
        return
    try:
        while length > 0:
            chunk = stream.read(min(65536, length))
            if not chunk:
                break
            length -= len(chunk)
    except Exception:
        pass


@blueprint.errorhandler(RequestEntityTooLarge)
def too_large(error):
    """The app refuses anything over MAX_CONTENT_LENGTH before a route runs. For an upload
    that would be a bare error page: say it plainly and go back to the device or note."""
    if request.endpoint != "attachments.upload":
        return error
    _drain_body()
    args = request.view_args or {}
    owner = None
    if args.get("owner_type") in OWNER_TYPES:
        owner = resolve_owner(args.get("owner_type"), args.get("owner_key"))
    flash(_too_big_message(), "danger")
    return _back(owner[3] if owner else None)
