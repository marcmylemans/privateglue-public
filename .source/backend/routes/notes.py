import os
import json
import markdown
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from flask_login import login_required
from backend.models.devices import Device
from backend.utils.rbac import admin_required, editor_required, readonly_required

notes_bp = Blueprint("notes", __name__, template_folder="../templates")
NOTES_DIR = "/app/notes"
META_FILE = os.path.join(NOTES_DIR, ".meta.json")

# === Helpers ===
def get_note_path(filename):
    return os.path.join(NOTES_DIR, filename)

def get_meta_path(filename):
    return os.path.join(NOTES_DIR, filename + ".meta.json")

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
            notes.append({
                "filename": filename,
                "tags": meta.get("tags", []),
                "device_ids": meta.get("device_ids", [])
            })
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
    all_devices = Device.query.all()

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
        all_devices=all_devices,
        all_tags=sorted(all_tags),
        filter_tag=filter_tag,
        filter_device=filter_device
    )

@notes_bp.route("/notes/<filename>")
@login_required
@readonly_required
def view_note(filename):
    filepath = get_note_path(filename)
    if not os.path.exists(filepath):
        return "Note not found", 404

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    html = markdown.markdown(content)
    meta = load_metadata(filename)
    devices = Device.query.filter(Device.id.in_(meta["device_ids"])).all()
    return render_template("notes/view.html", filename=filename, content=html, tags=meta["tags"], devices=devices)

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

        filename = filename.removesuffix(".md") + ".md"
        with open(get_note_path(filename), "w", encoding="utf-8") as f:
            f.write(content)

        save_metadata(filename, tags, device_ids)
        return redirect(url_for("notes.view_note", filename=filename))

    all_devices = Device.query.all()
    return render_template("notes/edit.html", create_mode=True, filename="", content="", tags="", linked_device_ids=[], all_devices=all_devices)

@notes_bp.route("/notes/edit/<filename>", methods=["GET", "POST"])
@login_required
@editor_required
def edit_note(filename):
    filepath = get_note_path(filename)
    if not os.path.exists(filepath):
        return "Note not found", 404

    if request.method == "POST":
        content = request.form.get("content", "")
        tags = request.form.get("tags", "").split(",")
        device_ids = request.form.getlist("devices")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        save_metadata(filename, tags, device_ids)
        return redirect(url_for("notes.view_note", filename=filename))

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    meta = load_metadata(filename)
    all_devices = Device.query.all()
    return render_template("notes/edit.html", create_mode=False, filename=filename, content=content, tags=", ".join(meta["tags"]), linked_device_ids=meta["device_ids"], all_devices=all_devices)

@notes_bp.route("/notes/delete/<filename>", methods=["POST"])
@login_required
@admin_required
def delete_note(filename):
    filepath = get_note_path(filename)
    meta_path = get_meta_path(filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    if os.path.exists(meta_path):
        os.remove(meta_path)
    flash(f"Note '{filename}' deleted.", "success")
    return redirect(url_for("notes.list_notes"))
