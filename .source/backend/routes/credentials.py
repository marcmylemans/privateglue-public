import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from backend.extensions import db
from backend.models.credentials import Credential
from backend.models.devices import Device
from backend.utils.encryption import fernet
from backend.utils.rbac import admin_required, editor_required, readonly_required

credentials_bp = Blueprint("credentials", __name__, template_folder="../templates")


@credentials_bp.route("/credentials")
@login_required
@readonly_required
def list_credentials():
    filter_device = request.args.get("device_id", type=int)
    all_devices = Device.query.all()
    
    query = Credential.query
    if filter_device:
        query = query.join(Credential.devices).filter(Device.id == filter_device)
    
    credentials = query.all()

    return render_template(
        "credentials/index.html",
        credentials=credentials,
        all_devices=all_devices,
        filter_device=filter_device
    )

@credentials_bp.route("/credentials/clear_filters")
@login_required
@readonly_required
def clear_filters():
    return redirect(url_for("credentials.list_credentials"))


@credentials_bp.route("/credentials/view/<int:id>")
@login_required
@readonly_required
def view_credential(id):
    cred = Credential.query.get_or_404(id)
    decrypted_password = cred.get_decrypted_password()
    return render_template("credentials/view.html", credential=cred, decrypted_password=decrypted_password)




@credentials_bp.route("/credentials/add", methods=["GET", "POST"])
@login_required
@editor_required
def add_credential():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        notes = request.form.get("notes", "").strip()
        device_ids = request.form.getlist("devices")

        cred = Credential(title=title, username=username, password=password, notes=notes)
        for device_id in device_ids:
            device = Device.query.get(int(device_id))
            if device:
                cred.devices.append(device)

        db.session.add(cred)
        db.session.commit()
        flash("Credential saved successfully.", "success")
        return redirect(url_for("credentials.list_credentials"))

    # Handle GET (prefill logic)
    all_devices = Device.query.all()
    device_id = request.args.get("device_id")
    default_title = ""
    linked_device_ids = []

    if device_id:
        device = Device.query.get(device_id)
        if device:
            default_title = device.hostname
            linked_device_ids = [device.id]

    return render_template(
        "credentials/form.html",
        create_mode=True,
        credential=None,
        prefilled_title=default_title,  # <- THIS LINE is the fix
        username="",
        password="",
        notes="",
        linked_device_ids=linked_device_ids,
        all_devices=all_devices
    )



@credentials_bp.route("/credentials/edit/<int:id>", methods=["GET", "POST"])
@login_required
@editor_required
def edit_credential(id):
    cred = Credential.query.get_or_404(id)

    if request.method == "POST":
        cred.title = request.form.get("title", "").strip()
        cred.username = request.form.get("username", "").strip()
        cred.password = request.form.get("password", "").strip()
        cred.notes = request.form.get("notes", "").strip()

        device_ids = request.form.getlist("devices")
        cred.devices = []
        for dev_id in device_ids:
            dev = Device.query.get(int(dev_id))
            if dev:
                cred.devices.append(dev)

        db.session.commit()
        flash("Credential updated successfully.", "success")
        return redirect(url_for("credentials.view_credential", id=cred.id))

    all_devices = Device.query.all()
    linked_device_ids = [d.id for d in cred.devices]

    return render_template(
        "credentials/form.html",
        credential=cred,
        create_mode=False,
        all_devices=all_devices,
        linked_device_ids=linked_device_ids,
        default_title=""
    )


@credentials_bp.route("/credentials/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
def delete_credential(id):
    cred = Credential.query.get_or_404(id)
    db.session.delete(cred)
    db.session.commit()
    flash("Credential deleted successfully.", "success")
    return redirect(url_for("credentials.list_credentials"))