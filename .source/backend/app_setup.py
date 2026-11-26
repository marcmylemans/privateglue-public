"""What the real app and the tests both need to show pages: the blueprints, the template
filters, the values every template gets, the error pages and the dashboard and search.

``backend/app.py`` builds the real app on top of this. Tests build a throw-away app with
the same function, so a test can open any page the way a browser would.
"""
import os
import re
from datetime import datetime

from flask import render_template, request
from flask_login import login_required
from markupsafe import Markup, escape

from backend import features
from backend.extensions import csrf, db
from backend.models.credentials import Credential
from backend.models.devices import Device
from backend.utils import paths


DEVICE_TYPE_ICONS = {
    "desktop": "pc-display", "laptop": "laptop", "server": "hdd-rack", "switch": "diagram-3",
    "router": "router", "accesspoint": "wifi", "printer": "printer", "firewall": "shield-lock",
    "nas": "device-hdd", "iot": "cpu", "vm": "boxes", "phone": "phone", "tablet": "tablet",
    "camera": "camera-video",
}


def register_blueprints(app):
    from backend.routes.admin import admin_bp
    from backend.routes.auth import auth_bp
    from backend.routes.credentials import credentials_bp
    from backend.routes.devices import api_discovered_devices, devices_bp
    from backend.routes.integrations import integrations_bp
    from backend.routes.network import network_bp
    from backend.routes.notes import notes_bp

    app.register_blueprint(devices_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(credentials_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(network_bp, url_prefix="/network")
    app.register_blueprint(integrations_bp)
    csrf.exempt(api_discovered_devices)
    features.init_app(app)


def register_template_helpers(app):
    @app.context_processor
    def inject_globals():
        from flask import current_app
        from flask_login import current_user
        role = getattr(current_user, "role", None)
        return {
            "DEMO_MODE": current_app.config.get("DEMO_MODE", False),
            "APP_NAME": current_app.config.get("APP_NAME", "PrivateGlue"),
            "APP_VERSION": paths.read_version(),
            "user_role": role,
            "can_edit": role in ("admin", "editor"),
            "is_admin": role == "admin",
        }

    @app.template_filter("device_icon")
    def device_icon_filter(device_type):
        return DEVICE_TYPE_ICONS.get((device_type or "").lower().replace(" ", ""), "box")


    @app.template_filter("type_label")
    def type_label_filter(device_type):
        labels = {"accesspoint": "Access point", "iot": "IoT", "vm": "VM", "nas": "NAS"}
        if not device_type:
            return ""
        return labels.get(device_type.lower().replace(" ", ""), device_type)


    @app.template_filter("note_title")
    def note_title_filter(filename):
        return (filename or "").removesuffix(".md")


    @app.template_filter("timeago")
    def timeago_filter(ts):
        if not ts:
            return ""
        delta = datetime.now() - datetime.fromtimestamp(ts)
        secs = int(delta.total_seconds())
        if secs < 60:
            return "just now"
        for unit, size in (("year", 31536000), ("month", 2592000), ("week", 604800), ("day", 86400), ("hour", 3600), ("minute", 60)):
            if secs >= size:
                n = secs // size
                return f"{n} {unit}{'s' if n != 1 else ''} ago"
        return "just now"


    @app.template_filter("highlight")
    def highlight_filter(text, query):
        """Escape text and wrap case-insensitive matches of query in <mark>."""
        text = "" if text is None else str(text)
        if not query:
            return escape(text)
        parts = re.split(f"({re.escape(query)})", text, flags=re.IGNORECASE)
        out = []
        for i, part in enumerate(parts):
            out.append(Markup("<mark>") + escape(part) + Markup("</mark>") if i % 2 else escape(part))
        return Markup("").join(out)

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    def server_error(error):
        return render_template("errors/500.html"), 500


def _note_snippet(text, query=None, width=140):
    """Plain-text snippet of a markdown note, centred on the first match when a query is given."""
    flat = re.sub(r"^\s*([-+*]|\d+\.)\s+", " ", text, flags=re.M)
    flat = re.sub(r"-{3,}|[#>*`_|]+", " ", flat)
    flat = re.sub(r"\s+", " ", flat).strip()
    if query:
        idx = flat.lower().find(query.lower())
        if idx > width // 2:
            start = idx - width // 2
            snippet = flat[start:start + width]
            return "…" + snippet + ("…" if start + width < len(flat) else "")
    return flat[:width] + ("…" if len(flat) > width else "")


def _load_notes_with_meta():
    from backend.routes.notes import load_metadata
    notes = []
    if not os.path.isdir(paths.NOTES_DIR):
        return notes
    for filename in os.listdir(paths.NOTES_DIR):
        if not filename.endswith(".md"):
            continue
        path = os.path.join(paths.NOTES_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue
        meta = load_metadata(filename)
        notes.append({
            "filename": filename,
            "content": content,
            "tags": meta.get("tags", []),
            "device_ids": meta.get("device_ids", []),
            "mtime": os.path.getmtime(path),
        })
    return notes


def register_core_routes(app):
    @app.route("/")
    @login_required
    def index():
        devices = Device.query.all()
        notes = _load_notes_with_meta()
        credential_count = Credential.query.count()

        by_type = {}
        for d in devices:
            key = d.device_type or "Other"
            by_type[key] = by_type.get(key, 0) + 1
        type_breakdown = sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0]))

        devices_by_id = {d.id: d for d in devices}
        recent_notes = []
        for n in sorted(notes, key=lambda n: n["mtime"], reverse=True)[:5]:
            recent_notes.append({
                "filename": n["filename"],
                "mtime": n["mtime"],
                "devices": [devices_by_id[i] for i in n["device_ids"] if i in devices_by_id],
            })

        recent_devices = Device.query.order_by(Device.id.desc()).limit(5).all()
        recent_credentials = Credential.query.order_by(Credential.id.desc()).limit(5).all()

        return render_template(
            "dashboard.html",
            device_count=len(devices),
            note_count=len(notes),
            credential_count=credential_count,
            location_count=len({d.location for d in devices if d.location}),
            type_breakdown=type_breakdown,
            recent_devices=recent_devices,
            recent_credentials=recent_credentials,
            recent_notes=recent_notes,
        )

    @app.route("/search")
    @login_required
    def search():
        query = request.args.get("q", "").strip()
        device_results, note_results, credential_results = [], [], []

        if query:
            like = f"%{query}%"
            device_results = Device.query.filter(
                db.or_(
                    Device.hostname.ilike(like),
                    Device.ip_address.ilike(like),
                    Device.mac_address.ilike(like),
                    Device.device_type.ilike(like),
                    Device.operating_system.ilike(like),
                    Device.location.ilike(like),
                    Device.serial_number.ilike(like),
                )
            ).order_by(Device.hostname).all()

            credential_results = Credential.query.filter(
                db.or_(Credential.title.ilike(like), Credential.username.ilike(like), Credential.address.ilike(like))
            ).order_by(Credential.title).all()

            q = query.lower()
            for n in _load_notes_with_meta():
                title_hit = q in n["filename"].lower()
                tag_hit = any(q in t.lower() for t in n["tags"])
                body_hit = q in n["content"].lower()
                if title_hit or tag_hit or body_hit:
                    note_results.append({
                        "filename": n["filename"],
                        "tags": n["tags"],
                        "snippet": _note_snippet(n["content"], query if body_hit else None),
                        "rank": 0 if title_hit else (1 if tag_hit else 2),
                    })
            note_results.sort(key=lambda n: (n["rank"], n["filename"]))

        return render_template(
            "search.html",
            query=query,
            devices=device_results,
            notes=note_results,
            credentials=credential_results,
            total=len(device_results) + len(note_results) + len(credential_results),
        )


def setup(app):
    """Everything above, in the order it has to happen."""
    register_blueprints(app)
    register_template_helpers(app)
    register_core_routes(app)
