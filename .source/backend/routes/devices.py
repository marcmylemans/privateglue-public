import os
import io, csv
import ipaddress
from backend.utils import audit
from backend import features
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, Response, jsonify, abort, current_app
from datetime import datetime
from flask_login import login_required, current_user
from backend.extensions import db, limiter
from backend.models.devices import Device
from backend.routes.notes import get_notes_linked_to_device
from backend.models.credentials import Credential
from backend.utils.rbac import admin_required, editor_required, readonly_required
from backend.utils.security import constant_time_equals
from backend.utils import netscan, probe_store
from backend.utils.proxmox import get_proxmox_client, fetch_proxmox_details
from proxmoxer import ProxmoxAPI
from requests.exceptions import HTTPError
from werkzeug.utils import secure_filename


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

    devices = query.order_by(db.func.lower(Device.hostname)).all()

    all_types = db.session.query(Device.device_type).distinct().all()
    all_locations = db.session.query(Device.location).distinct().all()

    discovered_count = 0
    try:
        discovered_count = len(probe_store.load_discovered()[0])
    except Exception:
        pass

    return render_template(
        "devices/index.html",
        devices=devices,
        filter_type=filter_type,
        filter_location=filter_location,
        all_types=sorted(t[0] for t in all_types if t[0]),
        all_locations=sorted(l[0] for l in all_locations if l[0]),
        discovered_count=discovered_count
    )


DEVICE_FIELDS = [
    "hostname", "ip_address", "mac_address", "device_type", "operating_system",
    "os_version", "serial_number", "license_key", "location",
]


def _device_form_context(**extra):
    """Values used by the device form for autocomplete suggestions."""
    def distinct(col):
        return sorted({v for (v,) in db.session.query(col).distinct() if v})
    ctx = {
        "known_locations": distinct(Device.location),
        "known_os": distinct(Device.operating_system),
    }
    ctx.update(extra)
    return ctx


def _apply_device_form(device):
    for field in DEVICE_FIELDS:
        value = (request.form.get(field) or "").strip()
        setattr(device, field, value or None)


@devices_bp.route("/devices/add", methods=["GET", "POST"])
@login_required
@editor_required
def add_device():
    if request.method == "POST":
        device = Device()
        _apply_device_form(device)
        if not device.hostname:
            flash("Hostname is required.", "danger")
            return render_template("devices/form.html", **_device_form_context(device=device, is_new=True))
        problems = features.problems("device_validate", request.form, None)
        if problems:
            for problem in problems:
                flash(problem, "danger")
            return render_template("devices/form.html", **_device_form_context(device=device, is_new=True))
        db.session.add(device)
        db.session.flush()  # gives the device its id, so features can store what belongs to it
        features.emit("device_saved", device, request.form, created=True)
        db.session.commit()
        audit.record("device.created", "device", device.id, device.hostname)
        flash(f"Device '{device.hostname}' added.", "success")
        return redirect(url_for("devices.view_device", id=device.id))

    return render_template("devices/form.html", **_device_form_context(device=None))


@devices_bp.route("/devices/edit/<int:id>", methods=["GET", "POST"])
@login_required
@editor_required
def edit_device(id):
    device = Device.query.get_or_404(id)

    if request.method == "POST":
        _apply_device_form(device)
        if not device.hostname:
            db.session.rollback()
            flash("Hostname is required.", "danger")
            return redirect(url_for("devices.edit_device", id=id))
        problems = features.problems("device_validate", request.form, device)
        if problems:
            db.session.rollback()
            for problem in problems:
                flash(problem, "danger")
            return redirect(url_for("devices.edit_device", id=id))
        features.emit("device_saved", device, request.form, created=False)
        db.session.commit()
        audit.record("device.updated", "device", device.id, device.hostname)
        flash(f"Device '{device.hostname}' saved.", "success")
        return redirect(url_for("devices.view_device", id=device.id))

    return render_template("devices/form.html", **_device_form_context(device=device))


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
    return render_template("devices/form.html", **_device_form_context(device=clone, clone=True, source=device))


@devices_bp.route("/devices/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
def delete_device(id):
    device = Device.query.get_or_404(id)
    hostname = device.hostname
    device.credentials = []
    features.emit("device_deleted", device)
    db.session.delete(device)
    db.session.commit()
    audit.record("device.deleted", "device", id, hostname)
    flash(f"Device '{hostname}' deleted.", "success")
    return redirect(url_for("devices.list_devices"))


@devices_bp.route("/devices/delete-selected", methods=["POST"])
@login_required
@admin_required
def delete_selected_devices():
    """Delete the devices ticked in the list. Useful after an import brought in too much."""
    ids = []
    for raw in request.form.getlist("ids"):
        try:
            ids.append(int(raw))
        except ValueError:
            continue
    devices = Device.query.filter(Device.id.in_(ids)).all() if ids else []
    deleted = [(device.id, device.hostname) for device in devices]
    for device in devices:
        device.credentials = []
        features.emit("device_deleted", device)
        db.session.delete(device)
    db.session.commit()
    for device_id, hostname in deleted:
        audit.record("device.deleted", "device", device_id, hostname)
    if devices:
        flash(f"{len(devices)} device{'s' if len(devices) != 1 else ''} deleted.", "success")
    else:
        flash("No devices were selected.", "warning")
    return redirect(url_for("devices.list_devices"))


@devices_bp.route("/devices/view/<int:id>")
@login_required
@readonly_required
def view_device(id):
    device = Device.query.get_or_404(id)
    linked_notes = get_notes_linked_to_device(device.id)
    credentials = device.credentials
    features.emit("device_viewed", device)

    return render_template(
        "devices/view.html",
        device=device,
        linked_notes=linked_notes,
        credentials=credentials,
        sources=_device_sources(device.id),
        snmp_eligible=_snmp_eligible(device),
        is_proxmox=(device.operating_system or "").lower() in ("proxmox", "proxmox ve"),
    )


def _device_sources(device_id):
    """Which integrations this device was synced from, for the "Synced from" line."""
    from backend import integrations
    from backend.integrations.devices import links_for_device
    sources = []
    for link in links_for_device(device_id):
        integration = integrations.get(link.integration)
        url = link.external_url if (link.external_url or "").startswith(("http://", "https://")) else None
        sources.append({"name": integration.name if integration else link.integration, "url": url})
    return sources


SNMP_TYPES = {"switch", "router", "accesspoint", "firewall"}


def _snmp_eligible(device):
    return bool(device.device_type and device.device_type.lower() in SNMP_TYPES)


@devices_bp.route("/devices/<int:id>/snmp-status")
@login_required
@readonly_required
def snmp_status(id):
    """Checked asynchronously by the device page so an unreachable host never slows it down."""
    device = Device.query.get_or_404(id)
    if not _snmp_eligible(device) or not device.ip_address:
        return jsonify({"available": False, "reason": "not-eligible"})
    try:
        from backend.utils.snmp import snmp_get
        # snmp_get() takes no timeout/retries arguments; passing them raised a TypeError
        # that was swallowed, so SNMP never showed as available before.
        sys_descr = snmp_get(device.ip_address, "1.3.6.1.2.1.1.1.0")
        return jsonify({"available": sys_descr is not None})
    except Exception:
        return jsonify({"available": False})


@devices_bp.route("/devices/<int:id>/credentials/add", methods=["GET", "POST"])
@login_required
@editor_required
def add_credential(id):
    device = Device.query.get_or_404(id)
    if request.method == "GET":
        return redirect(url_for("credentials.add_credential", device_id=device.id))
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
    if (device.operating_system or "").lower() not in ('proxmox', 'proxmox ve'):
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
        # The full error can contain internal addresses or parts of the request; keep it
        # in the server log and show only its kind.
        print(f"[proxmox] fetch failed for device {id}: {e}")
        flash(f"Could not fetch Proxmox info ({type(e).__name__}). Check the address and the linked credential.", "danger")
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

def _clean_discovered(entry):
    """Keep only the known device fields of a probe result, as short plain strings.
    The probe is outside the app, so nothing it sends is trusted."""
    clean = {}
    for field in DEVICE_FIELDS:
        value = entry.get(field)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            clean[field] = str(value).strip()[:255]
    # An entry is only useful with a real IP address; anything else is dropped by the caller.
    try:
        clean["ip_address"] = str(ipaddress.ip_address(clean.get("ip_address", "")))
    except ValueError:
        clean.pop("ip_address", None)
    return clean


@devices_bp.route('/api/discovered-devices', methods=['POST'])
@limiter.limit("30 per minute")
def api_discovered_devices():
    if not constant_time_equals(request.headers.get("X-API-KEY"), probe_store.get_api_key()):
        return jsonify({'status': 'error', 'error': 'Invalid or missing API key.'}), 401
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('devices'), list):
        return jsonify({'status': 'error', 'error': 'Expected JSON like {"devices": [...]}.'}), 400
    devices = data['devices']
    if len(devices) > probe_store.MAX_DEVICES:
        return jsonify({'status': 'error', 'error': f'Too many devices (limit {probe_store.MAX_DEVICES}).'}), 413
    cleaned = [c for c in (_clean_discovered(d) for d in devices if isinstance(d, dict)) if c.get('ip_address')]
    probe_store.save_discovered(cleaned)
    return jsonify({'status': 'ok', 'count': len(cleaned)})


@devices_bp.route('/devices/discovered')
@login_required
@editor_required
def show_discovered_devices():
    discovered, batch, received_at = probe_store.load_discovered()

    # Fetch existing devices to check for duplicates
    existing_devices = Device.query.with_entities(Device.hostname, Device.ip_address, Device.mac_address).all()
    existing_hostnames = set(d.hostname.lower() for d in existing_devices if d.hostname)
    existing_ips = set(d.ip_address for d in existing_devices if d.ip_address)
    existing_macs = set(_mac_key(d.mac_address) for d in existing_devices if d.mac_address)

    combined_data = []
    for d in discovered:
        duplicate_fields = []
        if d.get('hostname') and d['hostname'].lower() in existing_hostnames:
            duplicate_fields.append('hostname')
        if d.get('ip_address') in existing_ips:
            duplicate_fields.append('ip_address')
        if d.get('mac_address') and _mac_key(d['mac_address']) in existing_macs:
            duplicate_fields.append('mac_address')
        combined_data.append((d, duplicate_fields))

    is_admin = getattr(current_user, "role", None) == "admin"
    return render_template(
        'devices/discovered.html', combined_data=combined_data, batch=batch,
        received_at=datetime.utcfromtimestamp(received_at) if received_at else None,
        probe_key=probe_store.get_api_key() if is_admin else None,
        probe_server=request.url_root.rstrip('/'),
        scan_enabled=netscan.is_enabled(),
        scan_policy=netscan.policy(),
        scan_state=netscan.read_state() if netscan.is_enabled() else {"status": "idle"},
        scan_suggestion=netscan.suggested_network() if (netscan.is_enabled() and is_admin) else "",
        scan_server_address=netscan.server_address() if (netscan.is_enabled() and is_admin) else "",
    )


def _mac_key(value):
    """A MAC without separators and in lower case, so AA-BB-.. and aa:bb:.. compare equal."""
    return "".join(c for c in str(value).lower() if c in "0123456789abcdef")


@devices_bp.route('/devices/discovered/import', methods=['POST'])
@login_required
@editor_required
def import_discovered_devices():
    discovered, batch, _ = probe_store.load_discovered()
    # The checkboxes refer to positions in the list. If the probe sent a new list after the
    # page was opened, those positions now mean other devices: ask to review again.
    if request.form.get('batch', '') != batch:
        flash('The probe sent a new list in the meantime. Review it again before importing.', 'warning')
        return redirect(url_for('devices.show_discovered_devices'))

    selected = set(request.form.getlist('selected'))
    existing_devices = Device.query.with_entities(Device.hostname, Device.ip_address, Device.mac_address).all()
    existing_set = set((d.hostname, d.ip_address, d.mac_address) for d in existing_devices)

    created = 0
    for idx, d in enumerate(discovered):
        if str(idx) not in selected or not d.get('ip_address'):
            continue
        if (d.get('hostname'), d.get('ip_address'), d.get('mac_address')) in existing_set:
            continue
        db.session.add(Device(
            hostname=d.get('hostname') or d.get('ip_address'),
            ip_address=d.get('ip_address'),
            mac_address=d.get('mac_address'),
            device_type=d.get('device_type'),
            operating_system=d.get('operating_system'),
            os_version=d.get('os_version'),
            serial_number=d.get('serial_number'),
            license_key=d.get('license_key'),
            location=d.get('location'),
        ))
        created += 1

    db.session.commit()
    probe_store.clear_discovered()
    flash(f'Imported {created} discovered devices.', 'success')
    return redirect(url_for('devices.list_devices'))


@devices_bp.route('/devices/discovered/clear', methods=['POST'])
@login_required
@editor_required
def clear_discovered_devices():
    probe_store.clear_discovered()
    flash('The discovered list was cleared.', 'info')
    return redirect(url_for('devices.show_discovered_devices'))


@devices_bp.route('/devices/discovered/scan/setting', methods=['POST'])
@login_required
@admin_required
def set_server_scan():
    """The switch that allows or forbids scanning from the server. Administrators only."""
    if current_app.config.get("DEMO_MODE"):
        flash("Scanning is turned off in demo mode.", "warning")
        return redirect(url_for('devices.show_discovered_devices'))
    turn_on = request.form.get('enabled') == 'on'
    try:
        netscan.set_enabled(turn_on, by=current_user.username)
        audit.record("settings.server_scan_changed",
                     detail="Scanning from this server was turned " + ("on." if turn_on else "off."))
        print(f"[INFO] Scan from this server turned {'on' if turn_on else 'off'} by {current_user.username}")
        flash('Scanning from this server is now on.' if turn_on else 'Scanning from this server is now off.',
              'success' if turn_on else 'info')
    except netscan.ScanError as exc:
        flash(str(exc), 'danger')
    return redirect(url_for('devices.show_discovered_devices') + '#server-scan')


@devices_bp.route('/devices/discovered/scan', methods=['POST'])
@login_required
@admin_required
def scan_from_server():
    """Start a scan of one private network from the server itself (only when enabled)."""
    if current_app.config.get("DEMO_MODE"):
        flash("Scanning is turned off in demo mode.", "warning")
        return redirect(url_for('devices.show_discovered_devices'))
    try:
        network, _ = netscan.start_scan(request.form.get('network', ''), use_tcp=request.form.get('use_tcp') == 'on')
        flash(f'Scanning {network}. This page refreshes by itself until the scan is done.', 'info')
    except netscan.ScanError as exc:
        flash(str(exc), 'danger')
    return redirect(url_for('devices.show_discovered_devices') + '#server-scan')


@devices_bp.route('/devices/discovered/rotate-key', methods=['POST'])
@login_required
@admin_required
def rotate_probe_key():
    probe_store.rotate_api_key()
    audit.record("settings.probe_key_replaced")
    flash('New probe key created. Update the key on every machine that runs the probe.', 'success')
    return redirect(url_for('devices.show_discovered_devices'))
