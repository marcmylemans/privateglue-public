import os
from flask import Blueprint, render_template, request, redirect, url_for, session
from flask_login import login_required
from backend.extensions import db
from backend.models.devices import Device
from backend.routes.notes import get_notes_linked_to_device
from backend.models.credentials import Credential
from backend.utils.rbac import admin_required, editor_required, readonly_required


devices_bp = Blueprint("devices", __name__, template_folder="../templates")

# --- ROUTES ---

@devices_bp.route("/devices/clear_filters")
@login_required
@readonly_required
def clear_filters():
    session.pop("filter_type", None)
    session.pop("filter_location", None)
    return redirect(url_for("devices.list_devices"))


@devices_bp.route("/devices")
@login_required
@readonly_required
def list_devices():
    # Step 1: Immediately clear and redirect if needed
    if "clear" in request.args:
        session.pop("filter_type", None)
        session.pop("filter_location", None)
        return redirect(url_for("devices.list_devices"))

    # Step 2: Read filters
    filter_type = request.args.get("type")
    filter_location = request.args.get("location")

    # Step 3: Store in session if they came from request args
    if filter_type is not None or filter_location is not None:
        session["filter_type"] = filter_type
        session["filter_location"] = filter_location
    else:
        filter_type = session.get("filter_type")
        filter_location = session.get("filter_location")

    # Step 4: Build the filtered query
    query = Device.query
    if filter_type:
        query = query.filter(Device.device_type == filter_type)
    if filter_location:
        query = query.filter(Device.location == filter_location)

    devices = query.all()

    all_types = db.session.query(Device.device_type).distinct().all()
    all_locations = db.session.query(Device.location).distinct().all()

    return render_template(
        "devices/index.html",
        devices=devices,
        filter_type=filter_type,
        filter_location=filter_location,
        all_types=[t[0] for t in all_types if t[0]],
        all_locations=[l[0] for l in all_locations if l[0]],
    )


@devices_bp.route("/devices/add", methods=["GET", "POST"])
@login_required
@editor_required
def add_device():
    if request.method == "POST":
        device = Device(
            hostname=request.form["hostname"],
            ip_address=request.form["ip_address"],
            device_type=request.form["device_type"],
            location=request.form["location"],
        )
        db.session.add(device)
        db.session.commit()
        return redirect(url_for("devices.list_devices"))
    return render_template("devices/form.html", device=None)


@devices_bp.route("/devices/edit/<int:id>", methods=["GET", "POST"])
@login_required
@editor_required
def edit_device(id):
    device = Device.query.get_or_404(id)

    if request.method == "POST":
        device.hostname = request.form["hostname"]
        device.ip_address = request.form["ip_address"]
        device.device_type = request.form["device_type"]
        device.location = request.form["location"]
        db.session.commit()
        return redirect(url_for("devices.list_devices"))

    related_notes = get_notes_linked_to_device(device.id)

    return render_template("devices/form.html", device=device, related_notes=related_notes)


@devices_bp.route("/devices/clone/<int:id>", methods=["GET"])
@login_required
@editor_required
def clone_device(id):
    device = Device.query.get_or_404(id)

    # Create a clone-like object but do NOT add it to the DB yet
    clone = Device(
        hostname=f"{device.hostname}-copy",
        ip_address="",
        device_type=device.device_type,
        location=device.location
    )
    return render_template("devices/form.html", device=clone, clone=True)


@devices_bp.route("/devices/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
def delete_device(id):
    device = Device.query.get_or_404(id)
    db.session.delete(device)
    db.session.commit()
    return redirect(url_for("devices.list_devices"))


@devices_bp.route("/devices/view/<int:id>")
@login_required
@readonly_required
def view_device(id):
    device = Device.query.get_or_404(id)
    linked_notes = get_notes_linked_to_device(device.id)
    credentials = device.credentials  # ✅ FIXED here

    return render_template("devices/view.html", device=device, linked_notes=linked_notes, credentials=credentials)



@devices_bp.route("/devices/<int:id>/credentials/add", methods=["GET", "POST"])
@login_required
@readonly_required
def add_credential(id):
    device = Device.query.get_or_404(id)
    if request.method == "POST":
        credential = Credential(
            title=request.form["title"],
            username=request.form.get("username"),
            password=request.form.get("password"),
            notes=request.form.get("notes"),
            device=device
        )
        db.session.add(credential)
        db.session.commit()
        return redirect(url_for("devices.view_device", id=id))

    return render_template("credentials/form.html", device=device, credential=None)

@devices_bp.route("/devices/<int:id>/credentials/edit/<int:cred_id>", methods=["GET", "POST"])
@login_required
@editor_required
def edit_credential(id, cred_id):
    credential = Credential.query.get_or_404(cred_id)
    if request.method == "POST":
        credential.title = request.form["title"]
        credential.username = request.form.get("username")
        credential.password = request.form.get("password")
        credential.notes = request.form.get("notes")
        db.session.commit()
        return redirect(url_for("devices.view_device", id=id))

    return render_template("credentials/form.html", device=credential.device, credential=credential)

@devices_bp.route("/devices/<int:id>/credentials/delete/<int:cred_id>", methods=["POST"])
@login_required
@admin_required
def delete_credential(id, cred_id):
    credential = Credential.query.get_or_404(cred_id)
    db.session.delete(credential)
    db.session.commit()
    return redirect(url_for("devices.view_device", id=id))
