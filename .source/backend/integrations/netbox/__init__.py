"""NetBox integration: one-way import of devices (and optionally virtual machines).

Read-only towards NetBox. Targets NetBox 3.7 up to 4.x (checked against the 3.7, 4.0 to 4.5
and current main source). Where the API shape differs between versions this module reads
both shapes:

- device role: ``role`` (3.6 and later) or ``device_role`` (3.x, removed in 4.0)
- web link: ``display_url`` (4.1 and later), otherwise built from the address
- config context: skipped with ``exclude=config_context`` (up to 4.5) and
  ``omit=config_context`` (newer); each version ignores the parameter it does not know
- tokens: v2 tokens (``nbt_<key>.<secret>``, NetBox 4.5 and later) use the ``Bearer``
  scheme, classic v1 tokens use ``Token``
"""
import re

import requests

from backend.integrations import Field, Integration, IntegrationError, SyncResult
from backend.integrations.devices import upsert_device
from backend.integrations.http import request_json

PAGE_SIZE = 200      # NetBox caps a page at MAX_PAGE_SIZE (1000 by default)
MAX_PAGES = 500      # safety cap: 100,000 objects per query

DEVICES_PATH = "/api/dcim/devices/"
VMS_PATH = "/api/virtualization/virtual-machines/"
WEB_PATHS = {"device": "/dcim/devices/{id}/", "vm": "/virtualization/virtual-machines/{id}/"}

# PrivateGlue type values (as stored by the device form), with the words in a NetBox role
# name or slug that clearly mean that type. Checked in this order, first match wins.
_TYPE_RULES = [
    ("Firewall", {"firewall", "fw", "utm"}, ("firewall",)),
    ("AccessPoint", {"ap", "wap", "wifi", "wlan", "wireless"}, ("accesspoint",)),
    ("Router", {"router", "gateway", "rtr"}, ("router",)),
    ("Switch", {"switch", "sw"}, ("switch",)),
    ("NAS", {"nas", "storage", "san"}, ()),
    ("Printer", {"printer", "mfp", "mfd"}, ("printer",)),
    ("Camera", {"camera", "cctv", "nvr", "ipcam"}, ("camera",)),
    ("Server", {"server", "servers", "hypervisor", "host", "hosts"}, ("server",)),
    ("Laptop", {"laptop", "notebook"}, ("laptop",)),
    ("Desktop", {"desktop", "workstation", "pc"}, ("desktop", "workstation")),
    ("Phone", {"phone", "voip"}, ("phone",)),
    ("Tablet", {"tablet"}, ("tablet",)),
    ("IoT", {"iot", "sensor"}, ()),
    ("VM", {"vm"}, ("virtualmachine",)),
]


def map_role(*values):
    """Map a NetBox role name or slug to a PrivateGlue type, or None when nothing clearly fits."""
    for value in values:
        words = [w for w in re.split(r"[^a-z0-9]+", str(value or "").lower()) if w]
        joined = "".join(words)
        for type_value, word_set, substrings in _TYPE_RULES:
            if any(w in word_set for w in words) or any(s in joined for s in substrings):
                return type_value
    return None


def auth_header(token):
    """Return the Authorization header value for a NetBox token.

    v2 tokens (NetBox 4.5+) look like ``nbt_<key>.<secret>`` and use ``Bearer``; classic v1
    tokens are 40 hex characters and use ``Token``. A value pasted with its scheme already in
    front ("Bearer ..." or "Token ...") is used as given.
    """
    token = (token or "").strip()
    scheme, _, rest = token.partition(" ")
    if rest and scheme.lower() in ("bearer", "token"):
        scheme, token = scheme.capitalize(), rest.strip()
    elif token.startswith("nbt_"):
        scheme = "Bearer"
    else:
        scheme = "Token"
    if not token or any(c.isspace() for c in token):
        raise IntegrationError("The NetBox API token is empty or contains spaces. Paste it again.")
    return f"{scheme} {token}"


def split_list(text):
    return [part.strip() for part in str(text or "").split(",") if part.strip()]


def base_url(url):
    url = str(url or "").strip().rstrip("/")
    if url.endswith("/api"):
        url = url[:-4]
    return url


def _name(obj):
    """Name of a nested NetBox object (site, role, platform...), or ""."""
    if isinstance(obj, dict):
        return str(obj.get("name") or obj.get("display") or "").strip()
    return ""


def _address(obj):
    if isinstance(obj, dict):
        return obj.get("address") or ""
    return ""


def _mac(record):
    """MAC address when NetBox puts one on the device or VM itself.

    Current NetBox versions keep MAC addresses on interfaces only (``/api/dcim/interfaces/``),
    which this module does not read, so this is usually empty.
    """
    value = record.get("primary_mac_address")
    if isinstance(value, dict):
        value = value.get("mac_address") or value.get("display")
    return value or record.get("mac_address") or ""


def build_location(record):
    parts = [_name(record.get("site")), _name(record.get("location")), _name(record.get("rack"))]
    parts = [p for p in parts if p]
    if not parts and record.get("cluster"):
        parts = [_name(record.get("cluster"))]
    return " / ".join(parts)[:100]


def map_record(kind, record, netbox_url):
    """Turn one NetBox device or VM into (external_id, fields, external_url).

    Raises ValueError with a readable reason when the record cannot be imported.
    """
    if not isinstance(record, dict) or record.get("id") is None:
        raise ValueError("record without an id")
    object_id = record["id"]
    hostname = str(record.get("name") or "").strip()
    if not hostname and kind == "device":
        hostname = str(record.get("display") or "").strip()
    if not hostname:
        raise ValueError("has no name")

    role = record.get("role") or record.get("device_role")
    if kind == "vm":
        device_type = "VM"
    else:
        slug = role.get("slug") if isinstance(role, dict) else ""
        device_type = map_role(slug, _name(role)) or _name(role)

    fields = {
        "hostname": hostname,
        "ip_address": _address(record.get("primary_ip4")) or _address(record.get("primary_ip6")),
        "mac_address": _mac(record),
        "serial_number": record.get("serial") or "",
        "device_type": device_type,
        "operating_system": _name(record.get("platform")),
        "location": build_location(record),
    }
    external_url = record.get("display_url") or (
        netbox_url + WEB_PATHS[kind].format(id=object_id))
    return f"{kind}:{object_id}", fields, external_url


class NetBox(Integration):
    key = "netbox"
    name = "NetBox"
    description = "Imports devices, and optionally virtual machines, from NetBox into the device list."
    icon = "diagram-3"
    docs = "netbox.md"
    fields = [
        Field("url", "NetBox address", kind="url", required=True,
              placeholder="https://netbox.example.lan",
              help="The address you open NetBox on, without /api."),
        Field("api_token", "API token", kind="password", required=True,
              help="A read-only token. Both the newer nbt_ tokens and classic tokens work."),
        Field("verify_tls", "Verify the TLS certificate", kind="checkbox", default=True,
              help="Turn off only for a self-signed certificate."),
        Field("include_vms", "Import virtual machines too", kind="checkbox", default=False),
        Field("only_active", "Only import objects with status Active", kind="checkbox", default=True),
        Field("sites", "Only these sites", placeholder="site-a, site-b",
              help="Site slugs, comma separated. Empty means all sites."),
        Field("tags", "Only objects with one of these tags", placeholder="managed, homelab",
              help="Tag slugs, comma separated. Empty means no tag filter."),
        Field("overwrite", "Overwrite PrivateGlue values with NetBox values", kind="checkbox",
              default=False,
              help="Off: only empty fields are filled in. On: NetBox wins for every field it has a value for."),
    ]

    # --- HTTP -------------------------------------------------------------
    def _client(self, config):
        url = base_url(config.get("url"))
        if not url.startswith(("http://", "https://")):
            raise IntegrationError("The NetBox address must start with http:// or https://.")
        headers = {"Authorization": auth_header(config.get("api_token")),
                   "Accept": "application/json"}
        return url, headers, bool(config.get("verify_tls", True)), requests.Session()

    def _get(self, client, path, params=None):
        url, headers, verify, session = client
        return request_json("GET", url + path, headers=headers, params=params, verify=verify,
                            session=session, what="NetBox")

    def _list(self, client, path, params):
        """Yield every object of a list endpoint, page by page.

        Pages by offset on the configured address instead of following the ``next`` link,
        because NetBox behind a reverse proxy often builds ``next`` with the wrong scheme
        or host. ``next`` still tells when to stop.
        """
        offset = 0
        for _ in range(MAX_PAGES):
            page = self._get(client, path, list(params) + [("limit", PAGE_SIZE), ("offset", offset)])
            if not isinstance(page, dict) or not isinstance(page.get("results"), list):
                raise IntegrationError(f"NetBox returned an unexpected answer for {path}. Check the address.")
            results = page["results"]
            yield from results
            if not page.get("next") or not results:
                return
            offset += len(results)
        raise IntegrationError(
            f"Stopped after {MAX_PAGES} pages of {path}: more than {MAX_PAGES * PAGE_SIZE} objects. "
            "Narrow it down with the site or tag filter.")

    def _records(self, client, path, config):
        """All matching objects of one endpoint. Several tags mean "any of these tags"."""
        params = [("exclude", "config_context"), ("omit", "config_context")]
        if config.get("only_active", True):
            params.append(("status", "active"))
        params += [("site", slug) for slug in split_list(config.get("sites"))]
        tags = split_list(config.get("tags"))
        # NetBox matches ?tag=a&tag=b only when an object has ALL tags; run one query per tag.
        queries = [params + [("tag", tag)] for tag in tags] or [params]
        seen = set()
        for query in queries:
            for record in self._list(client, path, query):
                key = record.get("id") if isinstance(record, dict) else None
                if key is not None and key in seen:
                    continue
                seen.add(key)
                yield record

    # --- Integration API --------------------------------------------------
    def test(self, config):
        client = self._client(config)
        status = self._get(client, "/api/status/")
        if not isinstance(status, dict) or "netbox-version" not in status:
            raise IntegrationError("This address does not look like NetBox (no version in /api/status/).")
        page = self._get(client, DEVICES_PATH, [("limit", 1), ("brief", "true")])
        count = page.get("count") if isinstance(page, dict) else None
        message = f"Connected to NetBox {status['netbox-version']}"
        if isinstance(count, int):
            message += f", {count} devices visible to this token"
        return message

    def sync(self, config):
        client = self._client(config)
        overwrite = bool(config.get("overwrite"))
        result = SyncResult()
        counts = {"device": 0, "vm": 0}
        kinds = [("device", DEVICES_PATH)]
        if config.get("include_vms"):
            kinds.append(("vm", VMS_PATH))

        for kind, path in kinds:
            for record in self._records(client, path, config):
                counts[kind] += 1
                label = f"{'Device' if kind == 'device' else 'VM'} {self._label(record)}"
                try:
                    external_id, fields, external_url = map_record(kind, record, client[0])
                    _, action = upsert_device(self.key, external_id, fields,
                                              external_url=external_url, overwrite=overwrite)
                except (ValueError, TypeError, AttributeError, KeyError) as exc:
                    result.errors.append(f"{label}: skipped, {exc}")
                    continue
                if action == "created":
                    result.created += 1
                elif action == "updated":
                    result.updated += 1
                else:
                    result.skipped += 1

        message = f"Read {counts['device']} devices"
        if config.get("include_vms"):
            message += f" and {counts['vm']} virtual machines"
        result.message = message + " from NetBox"
        return result

    @staticmethod
    def _label(record):
        if not isinstance(record, dict):
            return "(unreadable record)"
        name = record.get("name") or record.get("display")
        return f"{name} (id {record.get('id')})" if name else f"id {record.get('id')}"


INTEGRATION = NetBox()
