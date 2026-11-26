"""Tags on credentials, the same way notes have them.

A credential gets a few short labels ("proxmox", "homelab"). They show as chips on the
credential page and in the list, and the list can be narrowed to one tag with ?tag=<name>.
Tags are not secret: they are plain text in their own table, linked by credential id.
"""
from flask import has_request_context, request, url_for

from backend.extensions import db
from backend.features import Feature
from backend.models.credentials import Credential

MAX_LENGTH = 40
MAX_PER_CREDENTIAL = 10
FIELD = "tags_names"


class CredentialTag(db.Model):
    __tablename__ = "credential_tag"
    __table_args__ = (db.UniqueConstraint("credential_id", "name", name="uq_credential_tag"),)

    id = db.Column(db.Integer, primary_key=True)
    credential_id = db.Column(db.Integer, db.ForeignKey("credential.id"), index=True, nullable=False)
    name = db.Column(db.String(MAX_LENGTH), nullable=False, index=True)


def clean_name(raw):
    """One tag as it is stored: printable, single spaces, trimmed, lower case, at most 40
    characters. Returns "" when nothing is left."""
    text = "".join(ch for ch in str(raw or "") if ch.isprintable() or ch.isspace())
    text = " ".join(text.split()).lower()
    return text[:MAX_LENGTH].strip()


def clean_tags(raw):
    """The comma separated text from the form, as a list of clean tags in the order typed.
    Empty ones and repeats are dropped and only the first ten are kept, silently, like the
    note form does."""
    out = []
    for part in str(raw or "").split(","):
        name = clean_name(part)
        if name and name not in out:
            out.append(name)
        if len(out) >= MAX_PER_CREDENTIAL:
            break
    return out


def _per_request():
    """A dict that lives as long as the current request (or a throw-away one outside a
    request). Not ``g``: that lives as long as the app context, which can be longer."""
    if not has_request_context():
        return {}
    return request.environ.setdefault("privateglue.tags", {})


class Tags(Feature):
    key = "tags"
    name = "Tags"
    order = 50

    # --- helpers for the templates ---------------------------------------------------------
    def _by_credential(self):
        """{credential id: [tag, ...]} for every credential, loaded once per request so the
        list page does not ask the database once per row."""
        store = _per_request()
        if "by_credential" not in store:
            cache = {}
            for row in CredentialTag.query.order_by(CredentialTag.id):
                cache.setdefault(row.credential_id, []).append(row.name)
            store["by_credential"] = cache
        return store["by_credential"]

    def for_credential(self, credential):
        if credential is None or not getattr(credential, "id", None):
            return []
        return list(self._by_credential().get(credential.id, []))

    def all_tags(self):
        """Every tag in use on a credential, sorted, each once."""
        names = set()
        for tags in self._by_credential().values():
            names.update(tags)
        return sorted(names)

    def active_filter(self):
        """The tag the list is narrowed to: {"name": ..., "applied": bool}, or None.
        "applied" is False when no credential has that tag; the list then shows everything
        (see credential_query)."""
        return _per_request().get("filter")

    def list_url(self, tag=None):
        """The credential list filtered on ``tag`` (None for all tags), keeping a device
        filter that is already active."""
        device_id = request.args.get("device_id", type=int) if has_request_context() else None
        return url_for("credentials.list_credentials", tag=tag or None, device_id=device_id or None)

    # --- hooks -----------------------------------------------------------------------------
    def credential_saved(self, credential, form, created, password_changed, old_password):
        if FIELD not in form:
            return  # not saved from the form that has the tags field: leave them alone
        CredentialTag.query.filter_by(credential_id=credential.id).delete(synchronize_session=False)
        for name in clean_tags(form.get(FIELD)):
            db.session.add(CredentialTag(credential_id=credential.id, name=name))
        _per_request().pop("by_credential", None)

    def credential_deleted(self, credential):
        CredentialTag.query.filter_by(credential_id=credential.id).delete(synchronize_session=False)
        _per_request().pop("by_credential", None)

    def credential_query(self, query, args):
        name = clean_name(args.get("tag"))
        if not name:
            return query
        tagged = db.session.query(CredentialTag.credential_id).filter(CredentialTag.name == name)
        narrowed = query.filter(Credential.id.in_(tagged))
        # The list page shows "No credentials yet" when the list comes back empty, with no
        # way back. So a tag nothing has (an old link, or a tag on credentials of another
        # device) leaves the list as it is, and the toolbar says so.
        applied = narrowed.first() is not None
        _per_request()["filter"] = {"name": name, "applied": applied}
        return narrowed if applied else query


FEATURE = Tags()
