import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from backend.extensions import db
from backend.models.credentials import Credential
from backend.models.devices import Device
from backend.utils.encryption import fernet
from backend.utils.rbac import admin_required, editor_required, readonly_required
from backend.utils import audit
from backend import features

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
    
    query = features.refine("credential_query", query, request.args)
    credentials = query.order_by(db.func.lower(Credential.title)).all()

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
    # The password is part of this page, so opening it counts as seeing the password.
    audit.record("credential.viewed", "credential", cred.id, cred.title)
    features.emit("credential_viewed", cred)
    db.session.commit()
    return render_template("credentials/view.html", credential=cred, decrypted_password=decrypted_password)




def _form_again(problems, cred):
    """A save was refused: show the form again with what was typed, so nobody has to start
    over. The password is the exception, it is never sent back to the browser."""
    for problem in problems:
        flash(problem, "danger")
    flash("Nothing was saved. Enter the password again if you had typed one.", "warning")
    title = request.form.get("title", "").strip()
    username = request.form.get("username", "").strip()
    notes = request.form.get("notes", "").strip()
    linked = [int(d) for d in request.form.getlist("devices") if d.isdigit()]
    all_devices = Device.query.order_by(db.func.lower(Device.hostname)).all()
    if cred is None:
        page = render_template("credentials/form.html", create_mode=True, credential=None,
                               prefilled_title=title, typed={"username": username, "notes": notes},
                               linked_device_ids=linked, all_devices=all_devices)
    else:
        cred.title, cred.username, cred.notes = title, username, notes
        page = render_template("credentials/form.html", create_mode=False, credential=cred,
                               linked_device_ids=linked, all_devices=all_devices, default_title="")
        db.session.rollback()  # the typed values were only for showing, nothing is stored
    return page, 400


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

        if not title:
            flash("Title is required.", "danger")
            return redirect(request.url)
        problems = features.problems("credential_validate", request.form, None)
        if problems:
            return _form_again(problems, None)

        cred = Credential(title=title, username=username, password=password, notes=notes)
        for device_id in device_ids:
            device = Device.query.get(int(device_id))
            if device:
                cred.devices.append(device)

        db.session.add(cred)
        db.session.flush()  # gives the credential its id, so features can store what belongs to it
        features.emit("credential_saved", cred, request.form, created=True,
                      password_changed=True, old_password=None)
        db.session.commit()
        audit.record("credential.created", "credential", cred.id, cred.title)
        flash(f"Credential '{cred.title}' saved.", "success")
        return redirect(url_for("credentials.view_credential", id=cred.id))

    # Handle GET (prefill logic)
    all_devices = Device.query.order_by(db.func.lower(Device.hostname)).all()
    device_id = request.args.get("device_id", type=int)
    default_title = ""
    linked_device_ids = []

    if device_id:
        device = db.session.get(Device, device_id)
        if device:
            default_title = f"{device.hostname} login"
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
        new_title = request.form.get("title", "").strip()
        if not new_title:
            flash("Title is required.", "danger")
            return redirect(request.url)
        problems = features.problems("credential_validate", request.form, cred)
        if problems:
            return _form_again(problems, cred)
        cred.title = new_title
        cred.username = request.form.get("username", "").strip()
        # The form says "leave blank to keep the current password", so only overwrite when filled in.
        new_password = request.form.get("password", "")
        old_password = None
        password_changed = False
        if new_password:
            old_password = cred.get_decrypted_password()
            password_changed = new_password != old_password
            cred.password = new_password
        cred.notes = request.form.get("notes", "").strip()

        device_ids = request.form.getlist("devices")
        cred.devices = []
        for dev_id in device_ids:
            dev = Device.query.get(int(dev_id))
            if dev:
                cred.devices.append(dev)

        features.emit("credential_saved", cred, request.form, created=False,
                      password_changed=password_changed,
                      old_password=old_password if password_changed else None)
        db.session.commit()
        audit.record("credential.updated", "credential", cred.id, cred.title,
                     detail="The password was changed." if password_changed else None)
        flash(f"Credential '{cred.title}' updated.", "success")
        return redirect(url_for("credentials.view_credential", id=cred.id))

    all_devices = Device.query.order_by(db.func.lower(Device.hostname)).all()
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
    title = cred.title
    features.emit("credential_deleted", cred)
    db.session.delete(cred)
    db.session.commit()
    audit.record("credential.deleted", "credential", id, title)
    flash(f"Credential '{title}' deleted.", "success")
    return redirect(url_for("credentials.list_credentials"))