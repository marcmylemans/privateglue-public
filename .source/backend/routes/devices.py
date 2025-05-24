import os
import io, csv
import secrets
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, Response, jsonify, abort
from flask_login import login_required
from backend.extensions import db
from backend.models.devices import Device
from backend.routes.notes import get_notes_linked_to_device
from backend.models.credentials import Credential
from backend.utils.rbac import admin_required, editor_required, readonly_required
from backend.utils.proxmox import get_proxmox_client, fetch_proxmox_details
from proxmoxer import ProxmoxAPI
from requests.exceptions import HTTPError
from werkzeug.utils import secure_filename


devices_bp = Blueprint("devices", __name__, template_folder="../templates")

discovered_devices_cache = []  # In-memory cache for demo; use DB for production

API_KEY_PATH = os.path.join(os.path.dirname(__file__), '../../data/probe_api_key.txt')
def get_or_create_probe_api_key():
    if os.path.exists(API_KEY_PATH):
        with open(API_KEY_PATH, 'r') as f:
            return f.read().strip()
    key = secrets.token_urlsafe(32)
    os.makedirs(os.path.dirname(API_KEY_PATH), exist_ok=True)
    with open(API_KEY_PATH, 'w') as f:
        f.write(key)
    return key
API_KEY = get_or_create_probe_api_key()

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

    discovered_count = 0
    try:
        from backend.routes.devices import discovered_devices_cache
        discovered_count = len(discovered_devices_cache)
    except Exception:
        pass

    return render_template(
        "devices/index.html",
        devices=devices,
        filter_type=filter_type,
        filter_location=filter_location,
        all_types=[t[0] for t in all_types if t[0]],
        all_locations=[l[0] for l in all_locations if l[0]],
        discovered_count=discovered_count
    )


@devices_bp.route("/devices/add", methods=["GET", "POST"])
@login_required
@editor_required
def add_device():
    if request.method == "POST":
        device = Device(
            hostname         = request.form["hostname"],
            ip_address       = request.form.get("ip_address"),
            mac_address      = request.form.get("mac_address"),
            device_type      = request.form["device_type"],
            operating_system = request.form.get("operating_system"),
            os_version       = request.form.get("os_version"),
            serial_number    = request.form.get("serial_number"),
            license_key      = request.form.get("license_key"),
            location         = request.form.get("location"),
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
        device.hostname         = request.form["hostname"]
        device.ip_address       = request.form.get("ip_address")
        device.mac_address      = request.form.get("mac_address")
        device.device_type      = request.form["device_type"]
        device.operating_system = request.form.get("operating_system")
        device.os_version       = request.form.get("os_version")
        device.serial_number    = request.form.get("serial_number")
        device.license_key      = request.form.get("license_key")
        device.location         = request.form.get("location")

        db.session.commit()
        return redirect(url_for("devices.list_devices"))

    related_notes = get_notes_linked_to_device(device.id)
    return render_template("devices/form.html", device=device, related_notes=related_notes)


@devices_bp.route("/devices/clone/<int:id>", methods=["GET"])
@login_required
@editor_required
def clone_device(id):
    device = Device.query.get_or_404(id)

    clone = Device(
        hostname         = f"{device.hostname}-copy",
        ip_address       = "",
        mac_address       = "",
        device_type      = device.device_type,
        operating_system = device.operating_system,
        os_version       = device.os_version,
        serial_number    = device.serial_number,
        license_key      = device.license_key,
        location         = device.location,
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

    # --- SNMP support for eligible device types ---
    SNMP_TYPES = {"switch", "router", "accesspoint", "firewall"}
    snmp_available = False
    snmp_error = None
    if device.device_type and device.device_type.lower() in SNMP_TYPES and device.ip_address:
        try:
            from backend.utils.snmp import snmp_get
            sys_descr = snmp_get(device.ip_address, "1.3.6.1.2.1.1.1.0")
            sys_uptime = snmp_get(device.ip_address, "1.3.6.1.2.1.1.3.0")
            if sys_descr or sys_uptime:
                snmp_available = True
        except Exception as e:
            snmp_error = str(e)

    return render_template(
        "devices/view.html",
        device=device,
        linked_notes=linked_notes,
        credentials=credentials,
        snmp_available=snmp_available,
        snmp_error=snmp_error,
        SNMP_TYPES=SNMP_TYPES
    )


@devices_bp.route("/devices/<int:id>/credentials/add", methods=["GET", "POST"])
@login_required
@editor_required
def add_credential(id):
    device = Device.query.get_or_404(id)
    if request.method == "POST":
        credential = Credential(
            title=request.form["title"],
            username=request.form.get("username"),
            password=request.form.get("password"),
            notes=request.form.get("notes"),
        )
        # link to devices (many-to-many)
        selected_ids = request.form.getlist("devices")
        credential.devices = Device.query.filter(Device.id.in_(selected_ids)).all()

        db.session.add(credential)
        db.session.commit()
        return redirect(url_for("devices.view_device", id=id))
    
    # GET: build a “dummy” credential object with defaults
    class _Defaults: pass
    defaults = _Defaults()
    defaults.title    = device.hostname         # prefill Title
    defaults.username = ""              # prefill Username
    defaults.notes    = ""
    defaults.devices  = [device]                # pre-select this device

    # fetch all devices for the multi-select
    all_devices = Device.query.order_by(Device.hostname).all()
    return render_template(
        "credentials/form.html",
        device=device,
        credential=defaults,
        all_devices=all_devices
    )

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

@devices_bp.route('/devices/<int:id>/fetch_info')
@login_required
@readonly_required
def fetch_device_info(id):
    device = Device.query.get_or_404(id)
    if device.operating_system.lower() not in ('proxmox', 'proxmox ve'):
        flash("Fetch only supported for Proxmox devices.", "warning")
        return redirect(url_for('devices.view_device', id=id))

    try:
        details = fetch_proxmox_details(device)
        return render_template(
            'devices/proxmox_info.html',
            device=device,
            details=details
        )
    except Exception as e:
        flash(f"Error fetching Proxmox info: {e}", "danger")
        return redirect(url_for('devices.view_device', id=id))

# Step 1: wizard entry point (GET shows form; POST processes upload)
@devices_bp.route('/devices/import', methods=['GET','POST'])
@login_required
@editor_required
def import_devices():
    expected_fields = [
        'hostname','ip_address','mac_address','device_type',
        'operating_system','os_version',
        'serial_number','license_key','location'
    ]
    if request.method == 'POST':
        # If mapping form was submitted
        if 'csv_content' in request.form:
            import json
            csv_content = request.form['csv_content']
            stream = io.StringIO(json.loads(csv_content))
            reader = csv.DictReader(stream)
            # Build mapping from form
            field_map = {field: request.form.get(f'map_{field}') for field in expected_fields}
            created = 0
            for row in reader:
                device_kwargs = {field: row.get(field_map[field]) for field in expected_fields if field_map[field]}
                if not device_kwargs.get('hostname'):
                    continue  # skip if no hostname
                device = Device(**device_kwargs)
                db.session.add(device)
                created += 1
            db.session.commit()
            flash(f'Successfully imported {created} devices (with mapping).', 'success')
            return redirect(url_for('devices.list_devices'))

        file = request.files.get('csvfile')
        if not file or not file.filename.endswith('.csv'):
            flash('Please upload a valid .csv file', 'danger')
            return redirect(request.url)

        # Try to decode with utf-8, fallback to utf-16 or latin-1
        file_bytes = file.stream.read()
        for encoding in ['utf-8-sig', 'utf-16', 'latin-1']:
            try:
                decoded = file_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                decoded = None
        if decoded is None:
            flash('Could not decode CSV file. Please ensure it is saved as UTF-8, UTF-16, or Latin-1.', 'danger')
            return redirect(request.url)

        stream = io.StringIO(decoded)
        reader = csv.DictReader(stream)
        csv_headers = reader.fieldnames
        if set(csv_headers) != set(expected_fields):
            # Headers do not match, show mapping form
            return render_template(
                'devices/import_map.html',
                csv_headers=csv_headers,
                expected_fields=expected_fields,
                csv_content=stream.getvalue()
            )

        # ...existing code for normal import...
        created = 0
        for row in reader:
            device = Device(
                hostname=row['hostname'],
                ip_address=row.get('ip_address'),
                mac_address=row.get('mac_address'),
                device_type=row.get('device_type'),
                operating_system=row.get('operating_system'),
                os_version=row.get('os_version'),
                serial_number=row.get('serial_number'),
                license_key=row.get('license_key'),
                location=row.get('location'),
            )
            db.session.add(device)
            created += 1

        db.session.commit()
        flash(f'Successfully imported {created} devices.', 'success')
        return redirect(url_for('devices.list_devices'))

    # GET → render upload/download form
    return render_template('devices/import.html')

# Step 2: serve the template CSV
@devices_bp.route('/devices/import/template')
@login_required
@editor_required
def import_devices_template():
    fieldnames = [
        'hostname','ip_address','mac_address','device_type',
        'operating_system','os_version',
        'serial_number','license_key','location'
    ]
    si = io.StringIO()
    csv.DictWriter(si, fieldnames=fieldnames).writeheader()
    return Response(
        si.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition':'attachment; filename=devices_template.csv'}
    )

@devices_bp.route('/api/discovered-devices', methods=['POST'])
def api_discovered_devices():
    if request.headers.get("X-API-KEY") != API_KEY:
        abort(401)
    data = request.get_json()
    devices = data.get('devices', [])
    global discovered_devices_cache
    discovered_devices_cache = devices
    return jsonify({'status': 'ok', 'count': len(devices)})

@devices_bp.route('/devices/discovered')
@login_required
@editor_required
def show_discovered_devices():
    global discovered_devices_cache

    # Fetch existing devices to check for duplicates
    existing_devices = Device.query.with_entities(Device.hostname, Device.ip_address, Device.mac_address).all()

    # Create sets for individual fields to check partial matches
    existing_hostnames = set(d.hostname for d in existing_devices if d.hostname)
    existing_ips = set(d.ip_address for d in existing_devices if d.ip_address)
    existing_macs = set(d.mac_address for d in existing_devices if d.mac_address)

    # Identify duplicates
    combined_data = []
    for d in discovered_devices_cache:
        duplicate_fields = []
        if d.get('hostname') in existing_hostnames:
            duplicate_fields.append('hostname')
        if d.get('ip_address') in existing_ips:
            duplicate_fields.append('ip_address')
        if d.get('mac_address') in existing_macs:
            duplicate_fields.append('mac_address')
        combined_data.append((d, duplicate_fields))

    return render_template('devices/discovered.html', combined_data=combined_data)

@devices_bp.route('/devices/discovered/import', methods=['POST'])
@login_required
@editor_required
def import_discovered_devices():
    global discovered_devices_cache
    selected = request.form.getlist('selected')
    created = 0

    # Fetch existing devices to check for duplicates
    existing_devices = Device.query.with_entities(Device.hostname, Device.ip_address, Device.mac_address).all()
    existing_set = set((d.hostname, d.ip_address, d.mac_address) for d in existing_devices)

    for idx, d in enumerate(discovered_devices_cache):
        if str(idx) not in selected:
            continue
        if not d.get('ip_address'):
            continue

        # Check for duplicates
        if (d.get('hostname'), d.get('ip_address'), d.get('mac_address')) in existing_set:
            continue

        device = Device(
            hostname=d.get('hostname') or d.get('ip_address'),
            ip_address=d.get('ip_address'),
            mac_address=d.get('mac_address'),
            device_type=d.get('device_type'),
            operating_system=d.get('operating_system'),
            os_version=d.get('os_version'),
            serial_number=d.get('serial_number'),
            license_key=d.get('license_key'),
            location=d.get('location'),
        )
        db.session.add(device)
        created += 1

    db.session.commit()
    discovered_devices_cache = []
    flash(f'Imported {created} discovered devices.', 'success')
    return redirect(url_for('devices.list_devices'))