"""Admin pages for integrations: list, settings, test connection, sync now."""
import os
import re

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required

from backend import integrations
from backend.extensions import db
from backend.integrations import runner
from backend.integrations.base import IntegrationError
from backend.integrations.models import IntegrationConfig, IntegrationRun
from backend.utils.rbac import admin_required

integrations_bp = Blueprint("integrations", __name__)

INTERVAL_CHOICES = [
    (0, "Manual only"), (15, "Every 15 minutes"), (60, "Every hour"),
    (360, "Every 6 hours"), (1440, "Once a day"), (10080, "Once a week"),
]


# The setup guides are the Markdown files under documentation/integrations. They are part of
# the image, so the guide can be read inside the app, also without internet access.
GUIDE_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "documentation", "integrations"))


def guide_path(key):
    """Path of an integration's guide, or None. Only plain keys are accepted, so a value
    such as "../../x" can never point outside the folder."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", key or ""):
        return None
    path = os.path.join(GUIDE_DIR, f"{key}.md")
    return path if os.path.isfile(path) else None


_LIST_ITEM = re.compile(r"^(\d+\.|[-*])\s")


def render_guide(text):
    """Markdown to safe HTML for the guides.

    The guides are written the way GitHub reads them (list text indented by three spaces,
    the next numbered step straight after an indented paragraph). The Markdown library is
    stricter, so give it the blank line and the indent width it needs, then clean the
    result with the same rules as notes.
    """
    import bleach
    import markdown
    from backend.routes.notes import ALLOWED_ATTRIBUTES, ALLOWED_PROTOCOLS, ALLOWED_TAGS

    lines, previous = [], ""
    for line in text.splitlines():
        if _LIST_ITEM.match(line) and previous.startswith(" ") and previous.strip():
            lines.append("")
        lines.append(line)
        previous = line
    html = markdown.markdown("\n".join(lines), extensions=["extra", "sane_lists"], tab_length=3)
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES,
                        protocols=ALLOWED_PROTOCOLS, strip=True)


def _get_or_404(key):
    integration = integrations.get(key)
    if integration is None:
        abort(404)
    return integration


def _demo_blocked():
    if current_app.config.get("DEMO_MODE"):
        flash("Integrations are turned off in demo mode.", "warning")
        return True
    return False


def apply_form(integration, row, form):
    """Copy the posted settings form onto the config row. Returns a list of problems."""
    settings, secrets = dict(row.settings), dict(row.secrets)
    problems = []
    for field in integration.fields:
        raw = (form.get(field.name) or "").strip()
        if field.kind == "checkbox":
            settings[field.name] = form.get(field.name) == "on"
            continue
        if field.secret:
            # Secrets are never sent to the browser. Empty means "keep what is saved";
            # the separate clear checkbox removes it.
            if form.get(f"clear_{field.name}") == "on":
                secrets.pop(field.name, None)
            elif raw:
                secrets[field.name] = raw
            if field.required and not secrets.get(field.name):
                problems.append(f"{field.label} is required.")
            continue
        if field.kind == "number" and raw:
            try:
                raw = int(raw)
            except ValueError:
                problems.append(f"{field.label} must be a number.")
                continue
        if field.kind == "select" and raw and raw not in [str(v) for v, _ in field.choices]:
            problems.append(f"{field.label} has an unknown value.")
            continue
        if field.kind == "url" and raw and not raw.lower().startswith(("http://", "https://")):
            problems.append(f"{field.label} must start with http:// or https://.")
            continue
        if field.required and raw == "":
            problems.append(f"{field.label} is required.")
        settings[field.name] = raw

    try:
        interval = int(form.get("interval_minutes") or 0)
    except ValueError:
        interval = 0
    row.interval_minutes = interval if interval in [v for v, _ in INTERVAL_CHOICES] else 0
    row.enabled = form.get("enabled") == "on"
    row.settings = settings
    row.secrets = secrets
    return problems


@integrations_bp.route("/admin/integrations")
@login_required
@admin_required
def list_integrations():
    rows = {r.key: r for r in IntegrationConfig.query.all()}
    items = [(i, rows.get(i.key)) for i in integrations.discover().values()]
    return render_template("integrations/index.html", items=items)


@integrations_bp.route("/admin/integrations/<key>", methods=["GET", "POST"])
@login_required
@admin_required
def configure(key):
    integration = _get_or_404(key)
    row = runner.get_or_create_config(key)

    if request.method == "POST":
        if _demo_blocked():
            db.session.rollback()
            return redirect(url_for("integrations.configure", key=key))
        problems = apply_form(integration, row, request.form)
        if problems and row.enabled:
            row.enabled = False
            problems.append("The integration stays turned off until this is fixed.")
        db.session.commit()
        for problem in problems:
            flash(problem, "danger")
        if not problems:
            flash(f"{integration.name} settings saved.", "success")
        return redirect(url_for("integrations.configure", key=key))

    db.session.commit()
    runs = (IntegrationRun.query.filter_by(key=key)
            .order_by(IntegrationRun.id.desc()).limit(10).all())
    return render_template(
        "integrations/configure.html",
        integration=integration, row=row, settings=row.settings,
        saved_secrets=set(row.secrets.keys()), runs=runs,
        interval_choices=INTERVAL_CHOICES, has_guide=bool(guide_path(integration.key)),
    )


@integrations_bp.route("/admin/integrations/<key>/guide")
@login_required
@admin_required
def guide(key):
    integration = _get_or_404(key)
    path = guide_path(integration.key)
    if not path:
        abort(404)
    with open(path, encoding="utf-8") as handle:
        html = render_guide(handle.read())
    return render_template("integrations/guide.html", integration=integration, content=html)


@integrations_bp.route("/admin/integrations/<key>/test", methods=["POST"])
@login_required
@admin_required
def test_connection(key):
    integration = _get_or_404(key)
    if _demo_blocked():
        return redirect(url_for("integrations.configure", key=key))
    row = runner.get_or_create_config(key)
    db.session.commit()
    config = runner.build_config(integration, row)
    missing = runner.missing_required(integration, config)
    if missing:
        flash("Save these settings first: " + ", ".join(missing), "warning")
        return redirect(url_for("integrations.configure", key=key))
    try:
        message = integration.test(config)
        flash(message or f"Connection to {integration.name} works.", "success")
    except IntegrationError as exc:
        flash(str(exc), "danger")
    except Exception as exc:
        flash(f"Unexpected error: {type(exc).__name__}: {exc}", "danger")
    return redirect(url_for("integrations.configure", key=key))


@integrations_bp.route("/admin/integrations/<key>/sync", methods=["POST"])
@login_required
@admin_required
def sync_now(key):
    integration = _get_or_404(key)
    if _demo_blocked():
        return redirect(url_for("integrations.configure", key=key))
    row = runner.get_or_create_config(key)
    db.session.commit()
    if not integration.can_sync:
        abort(404)
    if not row.enabled:
        flash(f"Turn {integration.name} on first.", "warning")
    elif row.running_since and not runner._claimable(row):
        flash("A sync is already running.", "info")
    else:
        runner.run_sync_in_background(current_app._get_current_object(), key, "manual")
        flash("Sync started. Reload this page in a moment to see the result.", "info")
    return redirect(url_for("integrations.configure", key=key))
