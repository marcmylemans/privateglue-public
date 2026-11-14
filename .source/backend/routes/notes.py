import os
import json
import markdown
import re
import bleach
from flask import abort
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from flask_login import login_required
from backend.models.devices import Device
from backend.utils.rbac import admin_required, editor_required, readonly_required
from werkzeug.utils import secure_filename
from backend.utils import paths

notes_bp = Blueprint("notes", __name__, template_folder="../templates")
NOTES_DIR = paths.NOTES_DIR
META_FILE = os.path.join(NOTES_DIR, ".meta.json")
NOTE_FILENAME_PATTERN = re.compile(r"^[\w\-. ]+\.md$")
ALLOWED_TAGS = [
    "p", "br", "pre", "code", "blockquote", "ul", "ol", "li",
    "strong", "em", "a", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "th", "td", "hr", "del", "img"
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "th": ["colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
    "code": ["class"],
    "img": ["src", "alt", "title"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def render_markdown(content):
    """Single rendering pipeline for the viewer and the editor preview."""
    raw_html = markdown.markdown(content or "", extensions=["extra", "sane_lists"])
    return bleach.clean(raw_html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES,
                        protocols=ALLOWED_PROTOCOLS, strip=True)


def note_excerpt(content, width=160):
    text = re.sub(r"```.*?```", " ", content or "", flags=re.S)
    text = re.sub(r"^#.*$", " ", text, flags=re.M)
    text = re.sub(r"^\s*([-+*]|\d+\.)\s+", " ", text, flags=re.M)
    text = re.sub(r"-{3,}|[#>*`_|\[\]()]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:width] + ("…" if len(text) > width else "")

# === Helpers ===
def normalize_note_filename(raw_filename):
    filename = (raw_filename or "").strip()
    if not filename:
        raise ValueError("Filename is required.")
    filename = filename.removesuffix(".md") + ".md"
    filename = secure_filename(filename)
    if not NOTE_FILENAME_PATTERN.match(filename):
        raise ValueError("Invalid filename. Use letters, numbers, spaces, dashes, underscores and .md.")
    return filename

def get_note_path(filename):
    resolved = os.path.realpath(os.path.join(NOTES_DIR, filename))
    notes_root = os.path.realpath(NOTES_DIR)
    if os.path.commonpath([notes_root, resolved]) != notes_root:
        raise ValueError("Invalid note path.")
    return resolved

def get_meta_path(filename):
    return get_note_path(filename + ".meta.json")

def load_metadata(filename):
    meta_path = get_meta_path(filename)
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                "tags": data.get("tags", []),
                "device_ids": data.get("device_ids", [])
            }
    return {"tags": [], "device_ids": []}

def save_metadata(filename, tags, device_ids):
    meta_path = get_meta_path(filename)
    data = {
        "tags": [t.strip() for t in tags if t.strip()],
        "device_ids": [int(d) for d in device_ids if str(d).isdigit()]
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_all_notes():
    notes = []
    for filename in os.listdir(NOTES_DIR):
        if filename.endswith(".md"):
            meta = load_metadata(filename)
            path = os.path.join(NOTES_DIR, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    excerpt = note_excerpt(f.read())
            except OSError:
                excerpt = ""
            notes.append({
                "filename": filename,
                "tags": meta.get("tags", []),
                "device_ids": meta.get("device_ids", []),
                "excerpt": excerpt,
                "mtime": os.path.getmtime(path),
            })
    notes.sort(key=lambda n: n["mtime"], reverse=True)
    return notes

def get_notes_linked_to_device(device_id):
    linked_notes = []
    for filename in os.listdir(NOTES_DIR):
        if filename.endswith(".meta.json"):
            meta_path = os.path.join(NOTES_DIR, filename)
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                device_ids = meta.get("device_ids", [])
                if int(device_id) in [int(d) for d in device_ids]:
                    note_name = filename.replace(".meta.json", "")
                    linked_notes.append(note_name)
    return linked_notes

def _all_tags():
    tags = set()
    for filename in os.listdir(NOTES_DIR):
        if filename.endswith(".md"):
            tags.update(load_metadata(filename)["tags"])
    return sorted(tags)

# === Routes ===
@notes_bp.route("/notes")
@login_required
def list_notes():
    filter_tag = request.args.get("tag")
    filter_device = request.args.get("device_id", type=int)
    clear = request.args.get("clear")

    if clear:
        session.pop("filter_tag", None)
        session.pop("filter_device", None)
        return redirect(url_for("notes.list_notes"))

    if filter_tag is not None:
        session["filter_tag"] = filter_tag
    else:
        filter_tag = session.get("filter_tag")

    if filter_device is not None:
        session["filter_device"] = filter_device
    else:
        filter_device = session.get("filter_device")

    notes = load_all_notes()
    all_devices = Device.query.order_by(Device.hostname).all()

    all_tags = set()
    for note in notes:
        all_tags.update(note["tags"])

    # Apply filters (access dict keys properly)
    if filter_tag:
        notes = [n for n in notes if filter_tag in n["tags"]]
    if filter_device:
        notes = [n for n in notes if filter_device in n["device_ids"]]

    return render_template(
        "notes/index.html",
        notes=notes,
        devices_by_id={d.id: d for d in all_devices},
        all_devices=all_devices,
        all_tags=sorted(all_tags),
        filter_tag=filter_tag,
        filter_device=filter_device
    )

@notes_bp.route("/notes/<filename>")
@login_required
@readonly_required
def view_note(filename):
    try:
        safe_filename = normalize_note_filename(filename)
        filepath = get_note_path(safe_filename)
    except ValueError:
        abort(404)
    if not os.path.exists(filepath):
        abort(404)

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    html = render_markdown(content)
    meta = load_metadata(safe_filename)
    devices = Device.query.filter(Device.id.in_(meta["device_ids"])).order_by(Device.hostname).all()
    return render_template("notes/view.html", filename=safe_filename, content=html, tags=meta["tags"],
                           devices=devices, mtime=os.path.getmtime(filepath),
                           word_count=len(content.split()))


@notes_bp.route("/notes/preview", methods=["POST"])
@login_required
@editor_required
def preview_note():
    """Renders the editor preview with exactly the same sanitiser as the note viewer."""
    return jsonify({"html": render_markdown(request.form.get("content", ""))})

@notes_bp.route("/notes/create", methods=["GET", "POST"])
@login_required
@editor_required
def create_note():
    if request.method == "POST":
        filename = request.form.get("filename", "").strip()
        content = request.form.get("content", "")
        tags = request.form.get("tags", "").split(",")
        device_ids = request.form.getlist("devices")

        if not filename:
            flash("Filename is required.", "danger")
            return redirect(url_for("notes.create_note"))

        try:
            filename = normalize_note_filename(filename)
            note_path = get_note_path(filename)
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("notes.create_note"))

        if os.path.exists(note_path):
            flash(f"A note called '{filename[:-3]}' already exists. Pick another title.", "danger")
            all_devices = Device.query.order_by(Device.hostname).all()
            return render_template("notes/edit.html", create_mode=True, filename=request.form.get("filename", ""),
                                   content=content, tags=request.form.get("tags", ""),
                                   linked_device_ids=[int(d) for d in device_ids if d.isdigit()],
                                   all_devices=all_devices, all_tags=_all_tags())

        with open(note_path, "w", encoding="utf-8") as f:
            f.write(content)

        save_metadata(filename, tags, device_ids)
        flash(f"Note '{filename[:-3]}' created.", "success")
        return redirect(url_for("notes.view_note", filename=filename))

    all_devices = Device.query.order_by(Device.hostname).all()
    preselect = request.args.get("device_id", type=int)
    return render_template("notes/edit.html", create_mode=True, filename="", content="", tags="",
                           linked_device_ids=[preselect] if preselect else [], all_devices=all_devices,
                           all_tags=_all_tags())

@notes_bp.route("/notes/edit/<filename>", methods=["GET", "POST"])
@login_required
@editor_required
def edit_note(filename):
    try:
        safe_filename = normalize_note_filename(filename)
        filepath = get_note_path(safe_filename)
    except ValueError:
        abort(404)
    if not os.path.exists(filepath):
        abort(404)

    if request.method == "POST":
        content = request.form.get("content", "")
        tags = request.form.get("tags", "").split(",")
        device_ids = request.form.getlist("devices")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        save_metadata(safe_filename, tags, device_ids)
        flash("Note saved.", "success")
        return redirect(url_for("notes.view_note", filename=safe_filename))

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    meta = load_metadata(safe_filename)
    all_devices = Device.query.order_by(Device.hostname).all()
    return render_template("notes/edit.html", create_mode=False, filename=safe_filename, content=content,
                           tags=", ".join(meta["tags"]), linked_device_ids=meta["device_ids"],
                           all_devices=all_devices, all_tags=_all_tags())

@notes_bp.route("/notes/delete/<filename>", methods=["POST"])
@login_required
@admin_required
def delete_note(filename):
    try:
        safe_filename = normalize_note_filename(filename)
        filepath = get_note_path(safe_filename)
        meta_path = get_meta_path(safe_filename)
    except ValueError:
        flash("Invalid filename.", "danger")
        return redirect(url_for("notes.list_notes"))
    if os.path.exists(filepath):
        os.remove(filepath)
    if os.path.exists(meta_path):
        os.remove(meta_path)
    flash(f"Note '{safe_filename[:-3]}' deleted.", "success")
    return redirect(url_for("notes.list_notes"))
