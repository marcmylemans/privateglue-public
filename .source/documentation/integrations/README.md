# Integrations

Integrations connect PrivateGlue to other systems you run: importing devices from another
inventory, keeping notes in a Git repository, and so on. You find them under
**Administration > Integrations** (admins only).

## For users

- Every integration is **off** until you turn it on and save its settings.
- **Test connection** checks the saved settings without changing anything.
- **Sync now** runs it once in the background. Reload the page to see the result in the run history.
- **Automatic sync** runs it on a schedule (15 minutes up to weekly). "Manual only" is the default.
- Tokens and passwords are stored encrypted with the same key as your credentials
  (`secret.key`), are included in backups in that encrypted form, and are never shown again
  after saving. Leave a token field empty to keep the saved one.
- Imports never delete devices. By default a sync only fills in fields that are empty in
  PrivateGlue, so what you typed by hand stays. Each integration says whether it offers an
  "overwrite" option.
- A device that an integration imported is matched again on its id in the other system. A
  device you created by hand first is adopted when the serial number, MAC address or hostname
  matches (in that order), so you do not get duplicates.
- In demo mode integrations cannot be saved or run.

Set `INTEGRATIONS_SCHEDULER=off` in `.env` to turn off automatic syncs completely
(manual "Sync now" keeps working).

Each integration has its own page in this folder, named after its key (for example `netbox.md`).

## For module authors

One integration is one package: `backend/integrations/<key>/__init__.py`. It is discovered
automatically. Do not edit `backend/app.py` or any shared list.

```python
from backend.integrations import Field, Integration, IntegrationError, SyncResult
from backend.integrations.devices import upsert_device
from backend.integrations.http import request_json


class Example(Integration):
    key = "example"                 # lowercase, also the folder name and the docs file name
    name = "Example"
    description = "One sentence on what it does."
    icon = "plug"                   # a Bootstrap icon name
    fields = [
        Field("url", "Address", kind="url", required=True, placeholder="https://example.lan"),
        Field("api_token", "API token", kind="password", required=True),
        Field("verify_tls", "Verify the TLS certificate", kind="checkbox", default=True),
    ]

    def test(self, config):
        data = request_json("GET", config["url"].rstrip("/") + "/api/status/",
                            headers={"Authorization": "Token " + config["api_token"]},
                            verify=config["verify_tls"], what="Example")
        return f"Connected to Example {data.get('version', '')}"

    def sync(self, config):
        result = SyncResult()
        for item in ...:
            try:
                _, action = upsert_device(self.key, item["id"], {"hostname": item["name"]})
            except ValueError as exc:
                result.errors.append(f"{item.get('id')}: {exc}")
                continue
            if action == "created": result.created += 1
            elif action == "updated": result.updated += 1
            else: result.skipped += 1
        return result


INTEGRATION = Example()
```

Rules:

- `config` is a dict of your field names with typed values (checkbox is `bool`, number is
  `int`, secrets are already decrypted).
- Raise `IntegrationError("message an admin can act on")` for expected failures. Never put a
  token in a message.
- Field kinds: `text`, `url`, `password`, `number`, `checkbox`, `select`, `textarea`. Any field
  whose name contains `token`, `password` or `secret` must be `kind="password"` (or `secret=True`).
- `sync` must not call `db.session.commit()` after a failure it wants rolled back; the runner
  commits once when `sync` returns and rolls back when it raises.
- Use `request_json` for HTTP so errors read the same everywhere. It uses `requests`, which
  is already a dependency. Always pass a timeout-friendly page size and follow pagination.
- Use `upsert_device` for devices. It handles matching, links and "fill blanks only".
- Ship `documentation/integrations/<key>.md` (what it does, how to create the token and which
  permissions it needs, every setting, what is and is not synced) and
  `tests/test_integration_<key>.py` built on `tests/integration_helpers.IntegrationTestCase`,
  with all HTTP mocked.
