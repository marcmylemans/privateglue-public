import os
import json
import markdown
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from flask_login import login_required
from backend.models.devices import Device
from backend.utils.rbac import admin_required, editor_required, readonly_required

notes_bp = Blueprint("notes", __name__, template_folder="../templates")
NOTES_DIR = "/app/notes"

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

def list_all_notes():
    return sorted([f for f in os.listdir(NOTES_DIR) if f.endswith(".md")])

def get_notes_linked_to_device(device_id):
    linked_notes = []
    for filename in os.listdir(NOTES_DIR):
        if filename.endswith(".meta.json"):
            meta_path = os.path.join(NOTES_DIR, filename)
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                device_ids = meta.get("device_ids", [])
                # Ensure device ID match (cast to int for safety)
                if int(device_id) in [int(d) for d in device_ids]:
                    note_name = filename.replace(".meta.json", "")
                    linked_notes.append(note_name)
    return linked_notes


# === Routes ===
@notes_bp.route("/notes")
@login_required
@readonly_required
def list_notes():
    if request.args.get("clear") == "1":
        session.pop("filter_tag", None)
        session.pop("filter_device", None)
        return redirect(url_for("notes.list_notes"))

    filter_tag = request.args.get("tag") or session.get("filter_tag")
    filter_device = request.args.get("device_id") or session.get("filter_device")

    if request.args.get("tag"):
        session["filter_tag"] = filter_tag
    if request.args.get("device_id"):
        session["filter_device"] = filter_device

    notes = []
    for filename in list_all_notes():
        note_id = filename[:-3]
        meta = load_metadata(filename)
        tags = meta["tags"]
        device_ids = meta["device_ids"]

        if filter_tag and filter_tag not in tags:
            continue
        if filter_device and str(filter_device) not in map(str, device_ids):
            continue

        notes.append({
            "filename": filename,
            "tags": tags,
            "device_ids": device_ids
        })

    all_devices = Device.query.all()
    return render_template("notes/index.html", notes=notes, filter_tag=filter_tag, filter_device=filter_device, all_devices=all_devices)

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
