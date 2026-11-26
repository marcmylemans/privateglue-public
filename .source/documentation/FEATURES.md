# Building a feature

A feature is an optional part of PrivateGlue that adds to the existing pages: tags on
credentials, an activity log, file attachments. Each one lives in its own folder and plugs
in through fixed points, so two features can be built at the same time without editing the
same files. This page is for whoever writes one.

Integrations (NetBox, UniFi and so on) are something else: they copy data from another
system. See `documentation/integrations/README.md` for those.

## Where the files go

| What | Where |
|---|---|
| Code: the `FEATURE` object, models, pages | `backend/features/<key>/__init__.py` (more modules in that folder are fine) |
| Pieces of existing pages | `backend/templates/features/<key>/<slot>.html` |
| Own pages | `backend/templates/features/<key>/<anything>.html` |
| Script, loaded on every page | `backend/static/js/features/<key>.js` |
| Styles, loaded on every page | `backend/static/css/features/<key>.css` |
| Tests | `tests/test_feature_<key>.py` |

`<key>` is short, lowercase, letters and underscores. A folder is found by itself at
start-up. Nothing has to be registered anywhere.

```python
# backend/features/tags/__init__.py
from flask import Blueprint
from backend.extensions import db
from backend.features import Feature

class CredentialTag(db.Model):            # a new table is created by itself
    __tablename__ = "credential_tag"
    id = db.Column(db.Integer, primary_key=True)
    credential_id = db.Column(db.Integer, db.ForeignKey("credential.id"), index=True, nullable=False)
    name = db.Column(db.String(60), nullable=False)

class Tags(Feature):
    key = "tags"
    name = "Tags"
    order = 50

    def for_credential(self, credential):          # templates call this as feat.tags.for_credential(c)
        return [t.name for t in CredentialTag.query.filter_by(credential_id=credential.id)]

    def credential_saved(self, credential, form, created, password_changed, old_password):
        ...                                        # db.session.add(...), no commit

    def credential_deleted(self, credential):
        CredentialTag.query.filter_by(credential_id=credential.id).delete()

FEATURE = Tags()
```

## Rules that keep features apart

1. Keep data in your **own tables**, linked by id (`credential_id`, `device_id`, a note's
   file name). Clean up in the `..._deleted` hook.
2. Only when a value truly belongs on an existing table: add the column to that model and
   declare it, `columns = {"credential": {"address": "TEXT"}}`. Existing installs then get
   the column at start-up. One feature per model, agree first.
3. Do not edit shared files: `custom.css`, `privateglue.js`, `base.html`, `_macros.html`,
   the page templates, the routes of other parts, `CHANGELOG.md`, the wiki. If a slot or a
   hook is missing, add it in a small separate change first.
4. Hooks run inside the caller's transaction. Use `db.session`, do not commit. The one
   exception is `audit_record`: it is called after the commit, so store and commit there.
5. Never put a secret in a log, an event, a URL or a flash message.
6. Secrets at rest are encrypted with `backend.utils.encryption.fernet`, like passwords.
7. Every route needs `@login_required` and a role check from `backend/utils/rbac.py`
   (`readonly_required` to look, `editor_required` to change, `admin_required` to
   administer). Forms carry `csrf_token`. Scripts in templates carry `nonce="{{ csp_nonce }}"`.
   No inline `onclick`, no assets from another site.

## Hooks

Methods on `Feature`; leave out what you do not need. Full text in
`backend/features/base.py`.

| Method | When |
|---|---|
| `credential_validate(form, credential)` | Before a save. Return messages to refuse it. `credential` is None for a new one. |
| `credential_saved(credential, form, created, password_changed, old_password)` | Filled in, has an id, not yet committed. |
| `credential_viewed(credential)` | The credential page was opened. |
| `credential_deleted(credential)` | Just before the delete. |
| `credential_query(query, args)` | Narrow the list. Return the query. |
| `device_validate`, `device_saved(device, form, created)`, `device_viewed`, `device_deleted` | The same for devices (form saves only, not imports or syncs). |
| `note_saved(filename, form, created)`, `note_deleted(filename)` | Notes are files; the name includes `.md`. |
| `user_deleted(user)` | Just before a user is deleted. |
| `audit_record(event)` | Something happened worth logging. See `backend/utils/audit.py`. |
| `backup_files()` | Extra files for a backup: `(path, "files/<key>/...")` pairs. Keep them in `paths.feature_files_dir("<key>")` and a restore puts them back. |
| `init_app(app)` | Once at start-up. |

To report something for the activity log from your own routes:
`audit.record("credential.code_copied", "credential", cred.id, cred.title)`.
A button can report a click with `data-audit="..." data-audit-target="credential:12"`.

## Slots

A slot is a place in an existing page. Create
`backend/templates/features/<key>/<slot>.html` and it is included there, with the page's
own values available. Pieces from several features appear in `order` (lower first).

A feature can give one slot its own position with `slot_order = {"<slot>": 15}` when a
piece belongs next to something that its normal order would separate it from.

Agreed order: address 10, one-time code 20, extra fields 30, password age 40, tags 50,
attachments 60, dates 70, two-factor 80, activity 90.

### Credential page (`credential` is the credential)

| Slot | Place | Write it as |
|---|---|---|
| `credential_view_header` | Buttons next to Edit | `<a class="btn btn-outline-secondary">` |
| `credential_view_meta` | Under the title, above the Login panel | a `<div class="mb-3">` with chips or a short line |
| `credential_view_login_top` | Login panel, above Username | `<div class="mb-3">` with label and `input-group`, like Username |
| `credential_view_login_bottom` | Login panel, under Password | `<div class="mt-3">`, same shape |
| `credential_view_panels` | Between Login and Notes | whole `<section class="panel">` |
| `credential_view_panels_bottom` | Above the danger zone | whole `<section class="panel">` |

### Credential form (`credential` is None when adding, `editing` is true when editing)

| Slot | Place | Write it as |
|---|---|---|
| `credential_form_after_title` | Under Title | `<div class="mb-3">` |
| `credential_form_after_password` | Under the password generator | `<div class="mt-3">` |
| `credential_form_sections` | After "Used on devices", before Notes | whole `<div class="form-section">` |

Field names are yours: prefix them with the feature key (`tags_names`) so two features
never share one. Read them from `form` in `credential_saved`.

### Credential list (`credential` is the row)

| Slot | Place | Write it as |
|---|---|---|
| `credential_list_toolbar` | Next to the filter box | a small control |
| `credential_list_th` / `credential_list_td` | A column after Username | `<th scope="col" class="d-none d-lg-table-cell">` and a matching `<td>` |
| `credential_list_title_extra` | Right of the title | small chips or a badge |
| `credential_list_filter_text` | Words the filter box also matches | plain text only, no tags |

### Device page and form (`device`, and `cred` inside the credentials list)

| Slot | Place | Write it as |
|---|---|---|
| `device_view_header` | Buttons before Duplicate | `<a class="btn btn-outline-secondary">` |
| `device_view_main_panels` | End of the wide column | whole `<section class="panel">` |
| `device_view_side_panels` | Narrow column, above the danger zone | whole `<section class="panel">` |
| `device_view_credential_item` | Inside a credential row, after the copy button | one icon button |
| `device_form_sections` | Before the Save button | whole `<div class="form-section">` with `form-section-title` |

### Elsewhere

| Slot | Place | Write it as |
|---|---|---|
| `dashboard_alerts` | A row between the counters and the lists; hidden when every piece is empty | `<div class="col-lg-6">` holding a panel, or nothing |
| `dashboard_panels` | End of the lists | `<div class="col-lg-6">` holding a panel |
| `note_view_main_panels` | Under the note text (`filename`) | whole `<section class="panel">` |
| `note_view_side_panels` | Under the tags box | whole `<section class="panel">` |
| `profile_panels` | Profile page, above the danger zone (`user`) | whole `<section class="panel">` |
| `nav_admin` | Menu, under "System & backups" (admins only) | `<a class="nav-link">` like the others |

## Look and feel

The app has one visual language. A feature that looks different is a bug.

* Use what `custom.css` already has: `panel`, `panel-header`, `panel-title`, `panel-body`,
  `facts`, `chip`, `chip-list`, `count-pill`, `mono`, `btn-ghost`, `item-list`,
  `form-section`, `form-text`, `optional`, `pg-table`, and the macros in `_macros.html`
  (`ui.copy_button`, `ui.empty_state`, `ui.delete_button`, `ui.fact`). Read a neighbouring
  panel and copy its shape.
* Colours only through the variables (`--pg-brand`, `--bs-body-color`, ...). Never a hex
  value, so light and dark both work.
* An empty piece shows nothing, or one quiet line with what to do. No empty boxes.
* Every icon button has an `aria-label`. Icons carry `aria-hidden="true"`. Links that open
  a new tab get `target="_blank" rel="noopener noreferrer"` and a hidden "(opens in a new tab)".
* Destructive actions use `ui.delete_button` or `data-confirm`, never `confirm()`.
* Text people read: short, plain, no em dashes.

## Tests

```python
from tests.feature_helpers import PageTestCase

class TagTests(PageTestCase):
    def test_tag_shows_on_the_credential(self):
        self.login("editor")
        self.client.post("/credentials/add", data={"title": "NAS", "password": "x", "tags_names": "lab"})
        self.assertIn("lab", self.page("/credentials"))
```

`PageTestCase` builds the whole app on a throw-away database with three users (`admin`,
`editor`, `readonly`). Run everything with `python -m unittest discover -s tests`; CI has
no pytest. Test at least: it shows, it saves, it is gone after a delete, a read-only user
cannot change it, and nothing secret leaks into the page source or the activity events.
