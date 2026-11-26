"""Extra fields: named values on a credential, encrypted like the password.

A login is often more than a username and a password: an SSH private key, an API token,
recovery codes, an account number. Each extra field has a label, a kind and a value:

* ``secret``     one line, hidden until shown;
* ``multiline``  several lines, hidden until shown (keys, recovery codes);
* ``text``       one line that is not secret, shown as is (an account or tenant id).

Every value is encrypted at rest, also ``text``. Secret values never go back into the edit
form: an empty value there keeps what is stored.

The form posts one ``fields_row`` per row, in page order, holding a short token. The other
inputs of that row are named after the token: ``fields_label_<token>``, ``fields_kind_<token>``,
``fields_value_<token>``, ``fields_id_<token>`` (existing fields only) and
``fields_remove_<token>``. Stored fields that the form does not mention are left alone, so
a post without this section (an older client, a script) never deletes anything.
"""
from backend.extensions import db
from backend.features import Feature
from backend.utils.encryption import fernet

KINDS = ("secret", "multiline", "text")
KIND_NAMES = {"secret": "Secret", "multiline": "Secret, several lines", "text": "Plain text"}
MAX_FIELDS = 20
MAX_LABEL = 80
MAX_VALUE = 16000


class CredentialField(db.Model):
    __tablename__ = "credential_field"
    id = db.Column(db.Integer, primary_key=True)
    credential_id = db.Column(db.Integer, db.ForeignKey("credential.id"), index=True, nullable=False)
    label = db.Column(db.String(MAX_LABEL), nullable=False, default="")
    kind = db.Column(db.String(16), nullable=False, default="secret")
    _value = db.Column("value", db.LargeBinary, nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)

    def set_value(self, value):
        self._value = fernet.encrypt((value or "").encode("utf-8"))

    def get_value(self):
        """The value in plain text, or None when it can no longer be decrypted."""
        try:
            return fernet.decrypt(self._value).decode("utf-8")
        except Exception:
            return None

    @property
    def hidden(self):
        return self.kind != "text"


def _clean_kind(kind):
    return kind if kind in KINDS else "secret"


def _clean_value(value, kind):
    """Line breaks as \\n only. A one-line kind loses a trailing line break; with line
    breaks inside it is stored as several lines, so nothing is cut off."""
    value = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    if kind != "multiline":
        stripped = value.strip("\n")
        if "\n" in stripped:
            return value, "multiline"
        return stripped, kind
    return value, kind


def _rows(form):
    """The posted rows, in page order, as plain dicts. Blank new rows are left out."""
    rows, seen = [], set()
    # A caller that is not the web form may pass a plain dict: then there are no rows.
    tokens = form.getlist("fields_row") if hasattr(form, "getlist") else []
    for token in tokens:
        token = (token or "").strip()
        if not token or token in seen or len(token) > 20:
            continue
        seen.add(token)
        raw_id = (form.get(f"fields_id_{token}") or "").strip()
        field_id = int(raw_id) if raw_id.isdigit() else None
        label = (form.get(f"fields_label_{token}") or "").strip()
        value, kind = _clean_value(form.get(f"fields_value_{token}"),
                                   _clean_kind(form.get(f"fields_kind_{token}")))
        remove = bool(form.get(f"fields_remove_{token}"))
        if field_id is None and (remove or (not label and not value)):
            continue
        rows.append({"id": field_id, "label": label, "kind": kind, "value": value, "remove": remove})
    return rows


def fields_of(credential_id):
    return (CredentialField.query.filter_by(credential_id=credential_id)
            .order_by(CredentialField.position, CredentialField.id).all())


class ExtraFields(Feature):
    key = "fields"
    name = "Extra fields"
    order = 30

    kinds = KINDS
    kind_names = KIND_NAMES
    max_fields = MAX_FIELDS
    max_label = MAX_LABEL
    max_value = MAX_VALUE

    # --- for the templates ---------------------------------------------------------------
    def for_credential(self, credential):
        """Fields of a credential for its page: dicts with the value decrypted (None when it
        cannot be read)."""
        if not credential or not credential.id:
            return []
        out = []
        for field in fields_of(credential.id):
            value = field.get_value()
            out.append({
                "id": field.id, "label": field.label, "kind": field.kind, "value": value,
                "lines": (value.rstrip("\n").count("\n") + 1) if value else 0,
            })
        return out

    def form_rows(self, credential):
        """Existing fields for the edit form. Hidden values are never included."""
        if not credential or not credential.id:
            return []
        rows = []
        for field in fields_of(credential.id):
            value = field.get_value() if field.kind == "text" else None
            rows.append({"id": field.id, "label": field.label, "kind": field.kind,
                         "value": value or "", "unreadable": field.kind == "text" and value is None})
        return rows

    # --- hooks ---------------------------------------------------------------------------
    def credential_validate(self, form, credential):
        rows = _rows(form)
        problems = []
        existing = {f.id for f in fields_of(credential.id)} if credential and credential.id else set()
        mentioned = {r["id"] for r in rows if r["id"] in existing}
        kept = len(existing - mentioned)
        for row in rows:
            if row["id"] in existing and row["remove"]:
                continue
            kept += 1
            if not row["label"]:
                problems.append("Each extra field needs a name.")
            if len(row["label"]) > MAX_LABEL:
                problems.append(f"Extra field names can be at most {MAX_LABEL} characters.")
            if len(row["value"]) > MAX_VALUE:
                problems.append(f"An extra field can hold at most {MAX_VALUE:,} characters.")
        if kept > MAX_FIELDS:
            problems.append(f"A credential can have at most {MAX_FIELDS} extra fields.")
        # One message of each sort is enough.
        return list(dict.fromkeys(problems))

    def credential_saved(self, credential, form, created, password_changed, old_password):
        existing = {f.id: f for f in fields_of(credential.id)}
        position = 0
        handled = set()
        for row in _rows(form):
            field = existing.get(row["id"])
            if field is not None and field.id in handled:
                field = None
            if field is not None:
                handled.add(field.id)
                if row["remove"]:
                    db.session.delete(field)
                    continue
                # Hidden values are not sent back to the form, so empty means "keep". A text
                # value is in the form, so empty means empty, unless it could not be read.
                current = field.get_value()
                kind = row["kind"]
                if row["value"] or (field.kind == "text" and current is not None):
                    field.set_value(row["value"])
                elif kind != "multiline" and current and "\n" in current.strip("\n"):
                    kind = "multiline"  # a kept value with line breaks cannot become one line
                field.label = row["label"][:MAX_LABEL]
                field.kind = kind
            else:
                if row["remove"] or (not row["label"] and not row["value"]):
                    continue
                field = CredentialField(credential_id=credential.id, label=row["label"][:MAX_LABEL],
                                        kind=row["kind"])
                field.set_value(row["value"])
                db.session.add(field)
            field.position = position
            position += 1
        # Fields the form did not mention keep their order, after the others.
        for field in existing.values():
            if field.id not in handled:
                field.position = position
                position += 1

    def credential_deleted(self, credential):
        CredentialField.query.filter_by(credential_id=credential.id).delete()


FEATURE = ExtraFields()
