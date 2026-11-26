"""Pages of the activity log: the admin page, its CSV export and the endpoint that takes
clicks reported by the browser."""
import csv
import io
import os
from datetime import datetime, timedelta, timezone

from flask import Blueprint, Response, abort, render_template, request, stream_with_context, url_for
from flask_login import current_user, login_required

from backend.extensions import db, limiter
from backend.features.audit import AuditEvent, wording
from backend.models.credentials import Credential
from backend.models.devices import Device
from backend.models.users import User
from backend.utils import audit
from backend.utils.rbac import admin_required, readonly_required

audit_bp = Blueprint("audit", __name__)

PER_PAGE = 50
EXPORT_MAX = 50000
PERIODS = {"today": "Today", "7d": "Last 7 days", "30d": "Last 30 days", "all": "All time"}


# --- time ------------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ago(when, now=None):
    """'just now', '5 minutes ago', 'yesterday', '3 days ago', or a date for old rows."""
    if not when:
        return ""
    secs = int(((now or _now()) - when).total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        n = secs // 60
        return f"{n} minute{'s' if n != 1 else ''} ago"
    if secs < 86400:
        n = secs // 3600
        return f"{n} hour{'s' if n != 1 else ''} ago"
    days = secs // 86400
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    return f"{when.day} {when.strftime('%b %Y')}"


def exact(when):
    """Exact time in UTC for a tooltip; the script turns it into the browser's local time."""
    return f"{when.day} {when.strftime('%b %Y, %H:%M:%S')} UTC" if when else ""


def _period_start(period):
    now = _now()
    if period == "today":
        local_midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        return local_midnight.astimezone(timezone.utc).replace(tzinfo=None)
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    return None


# --- filters ---------------------------------------------------------------------------

def _parse_target(raw):
    kind, _, ident = (raw or "").partition(":")
    if kind in ("credential", "device", "note", "user", "integration") and ident:
        return kind, ident[:255]
    return None


def _filters():
    args = request.args
    period = args.get("period", "all")
    kind = args.get("kind", "")
    return {
        "q": (args.get("q") or "").strip()[:100],
        "user": (args.get("user") or "").strip()[:80],
        "kind": kind if kind in wording.KINDS else "",
        "period": period if period in PERIODS else "all",
        "target": _parse_target(args.get("target")),
    }


def _query(f):
    query = AuditEvent.query
    if f["target"]:
        query = query.filter(AuditEvent.target_type == f["target"][0],
                             AuditEvent.target_id == f["target"][1],
                             AuditEvent.detached.is_(False))
    if f["user"]:
        query = query.filter(AuditEvent.username == f["user"])
    if f["kind"]:
        prefixes = wording.KINDS[f["kind"]][1]
        query = query.filter(db.or_(*[AuditEvent.action.startswith(p, autoescape=True) for p in prefixes]))
    start = _period_start(f["period"])
    if start is not None:
        query = query.filter(AuditEvent.at >= start)
    if f["q"]:
        like = f"%{f['q']}%"
        matching_actions = [a for a, s in wording.SENTENCES.items() if f["q"].lower() in s.lower()]
        conditions = [AuditEvent.username.ilike(like), AuditEvent.label.ilike(like),
                      AuditEvent.detail.ilike(like), AuditEvent.ip.ilike(like),
                      AuditEvent.action.ilike(like)]
        if matching_actions:
            conditions.append(AuditEvent.action.in_(matching_actions))
        query = query.filter(db.or_(*conditions))
    return query.order_by(AuditEvent.at.desc(), AuditEvent.id.desc())


def _filter_args(f, **extra):
    out = {k: f[k] for k in ("q", "user", "kind") if f[k]}
    if f["period"] != "all":
        out["period"] = f["period"]
    if f["target"]:
        out["target"] = f"{f['target'][0]}:{f['target'][1]}"
    out.update(extra)
    return {k: v for k, v in out.items() if v is not None}


# --- links to items that still exist ---------------------------------------------------

def _item_links(rows):
    """{row id: url} for rows whose item still exists. A few queries per page, not per row."""
    wanted = {}
    for row in rows:
        if row.target_type and row.target_id and not row.detached:
            wanted.setdefault(row.target_type, set()).add(row.target_id)

    def ids(kind):
        return {int(i) for i in wanted.get(kind, ()) if i.isdigit()}

    alive = {}
    if ids("credential"):
        alive["credential"] = {str(i) for (i,) in db.session.query(Credential.id).filter(Credential.id.in_(ids("credential")))}
    if ids("device"):
        alive["device"] = {str(i) for (i,) in db.session.query(Device.id).filter(Device.id.in_(ids("device")))}
    if ids("user"):
        alive["user"] = {str(i) for (i,) in db.session.query(User.id).filter(User.id.in_(ids("user")))}
    if wanted.get("note"):
        from backend.routes.notes import get_note_path
        found = set()
        for name in wanted["note"]:
            try:
                if os.path.isfile(get_note_path(name)):
                    found.add(name)
            except Exception:
                pass
        alive["note"] = found
    if wanted.get("integration"):
        from backend import integrations
        alive["integration"] = {k for k in wanted["integration"] if integrations.get(k) is not None}

    endpoints = {
        "credential": lambda i: url_for("credentials.view_credential", id=int(i)),
        "device": lambda i: url_for("devices.view_device", id=int(i)),
        "user": lambda i: url_for("admin.edit_user", user_id=int(i)),
        "note": lambda i: url_for("notes.view_note", filename=i),
        "integration": lambda i: url_for("integrations.configure", key=i),
    }
    links = {}
    for row in rows:
        if row.target_id in alive.get(row.target_type, ()):
            try:
                links[row.id] = endpoints[row.target_type](row.target_id)
            except Exception:
                pass
    return links


# --- pages -----------------------------------------------------------------------------

@audit_bp.route("/admin/activity")
@login_required
@admin_required
def activity():
    f = _filters()
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    query = _query(f)
    total = query.order_by(None).count()
    pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    page = min(page, pages)
    rows = query.offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()
    usernames = [u for (u,) in db.session.query(AuditEvent.username).filter(AuditEvent.username.isnot(None))
                 .distinct().order_by(AuditEvent.username)]
    if f["user"] and f["user"] not in usernames:
        usernames.append(f["user"])
    target_label = None
    if f["target"]:
        latest = AuditEvent.query.filter_by(target_type=f["target"][0], target_id=f["target"][1]) \
            .filter(AuditEvent.label.isnot(None)).order_by(AuditEvent.at.desc()).first()
        target_label = latest.label if latest else f"{f['target'][0]} {f['target'][1]}"
    filtered = any(_filter_args(f).values())
    return render_template(
        "features/audit/activity.html",
        rows=rows, links=_item_links(rows), filters=f, total=total, page=page, pages=pages,
        first=(page - 1) * PER_PAGE + 1 if rows else 0, last=(page - 1) * PER_PAGE + len(rows),
        usernames=usernames, kinds=wording.KINDS, periods=PERIODS, target_label=target_label,
        filtered=filtered, filter_args=lambda **extra: _filter_args(f, **extra),
        now=_now(), ago=ago, exact=exact, keep_days=365,
    )


def _safe_cell(value):
    """Stop a spreadsheet from running a cell as a formula."""
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


@audit_bp.route("/admin/activity/export.csv")
@login_required
@admin_required
def export():
    f = _filters()
    query = _query(f)
    count = min(query.order_by(None).count(), EXPORT_MAX)
    audit.record("audit.exported", detail=f"{count} row{'s' if count != 1 else ''}.")

    def generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["When (UTC)", "Who", "What", "Action", "Item type", "Item id", "Item", "Detail", "IP address"])
        for row in query.limit(EXPORT_MAX).yield_per(1000):
            writer.writerow([_safe_cell(v) for v in (
                row.at.strftime("%Y-%m-%d %H:%M:%S"), row.username, row.sentence, row.action,
                row.target_type, row.target_id, row.label, row.detail, row.ip)])
            if buffer.tell() > 64 * 1024:
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate()
        yield buffer.getvalue()

    stamp = _now().strftime("%Y-%m-%d")
    return Response(stream_with_context(generate()), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="activity-{stamp}.csv"',
                             "Cache-Control": "no-store"})


def _per_user_key():
    try:
        if current_user.is_authenticated:
            return f"audit-event:{current_user.id}"
    except Exception:
        pass
    return request.remote_addr or "unknown"


@audit_bp.route("/activity/event", methods=["POST"])
@limiter.limit("120 per minute", key_func=_per_user_key)
@login_required
@readonly_required
def browser_event():
    """A button in the page says what it did, for example "copied the password"."""
    action = (request.form.get("action") or "").strip()
    kind, _, ident = (request.form.get("target") or "").partition(":")
    if action not in wording.BROWSER_ACTIONS or kind != "credential" or not ident.isdigit():
        abort(400)
    credential = db.session.get(Credential, int(ident))
    if credential is None:
        abort(404)
    audit.record(action, "credential", credential.id, credential.title)
    return "", 204
