"""UniFi Network: import gateways, switches, access points and (optionally) clients.

Uses the official UniFi Network API (the "Integration API") that the UniFi Network
application serves locally since version 9.0. It authenticates with an API key created in
UniFi Network under Settings > Control Plane > Integrations, sent in the X-API-KEY header.

On a UniFi OS console (Cloud Gateway, UDM, UCG, Cloud Key, UniFi OS Server) the API lives
under /proxy/network/integration/v1. A self-hosted Network application without UniFi OS
serves it under /integration/v1. The module tries the first and falls back to the second.

Read-only: only GET requests are made.
"""
from urllib.parse import urlsplit

from backend.integrations import Field, Integration, IntegrationError, SyncResult
from backend.integrations.devices import normalize_mac, upsert_device
from backend.integrations.http import request_json

WHAT = "the UniFi console"
PAGE_SIZE = 200   # the API maximum for limit
MAX_PAGES = 100   # safety cap: 20 000 records per list

# Stored values of the PrivateGlue device type field (see templates/devices/form.html).
TYPE_ROUTER = "Router"
TYPE_ACCESS_POINT = "AccessPoint"
TYPE_SWITCH = "Switch"

# Base paths to try, in order, when the console address has no path of its own.
_PREFIXES = ("/proxy/network/integration/v1", "/integration/v1")


class Truncated(Exception):
    """Internal: a list was cut off at MAX_PAGES."""


def _text(value):
    if value is None:
        return ""
    return str(value).strip()


def device_type_for(features):
    """Map the device's ``features`` list to a PrivateGlue device type.

    A UniFi gateway (UDM, UCG, UXG, Dream Router) routes, firewalls and often also has
    switch ports or even a radio, so ``gateway`` wins. In-wall access points have switch
    ports too, so ``accessPoint`` wins over ``switching``.
    """
    if isinstance(features, dict):
        # The details endpoint returns an object ({"switching": {}, ...}): a key that is
        # present and not null means the device has that feature.
        features = [k for k, v in features.items() if v is not None]
    names = {str(f).lower() for f in (features or [])}
    if "gateway" in names:
        return TYPE_ROUTER
    if "accesspoint" in names:
        return TYPE_ACCESS_POINT
    if "switching" in names:
        return TYPE_SWITCH
    return ""


class UniFiNetwork(Integration):
    key = "unifi"
    name = "UniFi Network"
    description = ("Import UniFi gateways, switches and access points, and optionally connected "
                   "clients, from a UniFi Network console (read-only).")
    icon = "wifi"
    docs = "unifi.md"
    fields = [
        Field("url", "Console address", kind="url", required=True,
              placeholder="https://192.168.1.1",
              help="The address of your UniFi console or Network server, without a path."),
        Field("api_key", "API key", kind="password", required=True,
              help="Create it in UniFi Network under Settings > Control Plane > Integrations."),
        Field("verify_tls", "Verify the TLS certificate", kind="checkbox", default=True,
              help="UniFi consoles ship with a self-signed certificate. Turn this off unless you "
                   "installed a trusted certificate on the console."),
        Field("site_name", "Site name", kind="text", default="",
              placeholder="Default",
              help="Only import this site. Leave empty to import all sites."),
        Field("import_devices", "Import UniFi devices", kind="checkbox", default=True,
              help="Gateways, switches and access points adopted in UniFi Network."),
        Field("import_clients", "Import clients", kind="checkbox", default=False,
              help="Computers, servers, printers and other devices connected to the network."),
        Field("wired_clients_only", "Wired clients only", kind="checkbox", default=True,
              help="Skip Wi-Fi clients, so phones and guests do not flood the device list."),
        Field("overwrite", "Overwrite PrivateGlue values", kind="checkbox", default=False,
              help="Off: only fill in empty fields. On: UniFi values replace what is in PrivateGlue."),
    ]

    # --- HTTP -------------------------------------------------------------
    def _headers(self, config):
        return {"X-API-KEY": config.get("api_key") or "", "Accept": "application/json"}

    def _get(self, config, base, path, params=None):
        return request_json("GET", base + path, headers=self._headers(config), params=params,
                            verify=bool(config.get("verify_tls", True)), what=WHAT)

    def _paged(self, config, base, path):
        """Yield every record of a paginated list. Raises Truncated after MAX_PAGES."""
        offset = 0
        for _ in range(MAX_PAGES):
            page = self._get(config, base, path, params={"offset": offset, "limit": PAGE_SIZE})
            if not isinstance(page, dict):
                raise IntegrationError(f"{WHAT} returned an unexpected answer for {path}.")
            data = page.get("data") or []
            if not isinstance(data, list):
                raise IntegrationError(f"{WHAT} returned an unexpected answer for {path}.")
            for item in data:
                yield item
            if not data:
                return
            offset += len(data)
            total = page.get("totalCount")
            if isinstance(total, int) and offset >= total:
                return
            if total is None and len(data) < PAGE_SIZE:
                return
        raise Truncated(path)

    def _base_url(self, config):
        url = _text(config.get("url")).rstrip("/")
        if not url:
            raise IntegrationError("Fill in the console address.")
        return url

    def _connect(self, config):
        """Find the API base and return (base, sites)."""
        url = self._base_url(config)
        path = urlsplit(url).path
        if path:
            # The admin typed a path (for example https://host/proxy/network): use it as is.
            if path.endswith("/integration/v1"):
                candidates = [url]
            elif path.endswith("/integration"):
                candidates = [url + "/v1"]
            else:
                candidates = [url + "/integration/v1"]
        else:
            candidates = [url + p for p in _PREFIXES]
        last = None
        for base in candidates:
            try:
                sites = self._sites(config, base)
                return base, sites
            except IntegrationError as exc:
                if "404" not in str(exc):
                    raise
                last = exc
        raise IntegrationError(
            "No UniFi Network API found at this address (HTTP 404). Check the console address "
            "and that UniFi Network is version 9.0 or newer."
        ) from last

    def _sites(self, config, base):
        try:
            return [s for s in self._paged(config, base, "/sites") if isinstance(s, dict)]
        except Truncated:
            raise IntegrationError(f"{WHAT} returned more than {PAGE_SIZE * MAX_PAGES} sites.")

    def _selected_sites(self, config, sites):
        wanted = _text(config.get("site_name"))
        if not wanted:
            return sites
        chosen = [s for s in sites
                  if wanted.lower() in (_text(s.get("name")).lower(),
                                        _text(s.get("internalReference")).lower())]
        if not chosen:
            names = ", ".join(sorted(_text(s.get("name")) for s in sites if _text(s.get("name"))))
            raise IntegrationError(
                f'Site "{wanted}" was not found. Sites on this console: {names or "none"}.')
        return chosen

    # --- test -------------------------------------------------------------
    def test(self, config):
        base, sites = self._connect(config)
        selected = self._selected_sites(config, sites)
        version = ""
        try:
            info = self._get(config, base, "/info")
            if isinstance(info, dict):
                version = _text(info.get("applicationVersion"))
        except IntegrationError:
            pass  # /info is not on every version; the sites call already proved access
        prefix = f"Connected to UniFi Network {version}" if version else "Connected"
        count = len(sites)
        text = f"{prefix}, {count} site{'' if count == 1 else 's'} found"
        if _text(config.get("site_name")):
            text += f', importing site "{_text(selected[0].get("name"))}"'
        return text

    # --- sync -------------------------------------------------------------
    def sync(self, config):
        result = SyncResult()
        if not config.get("import_devices") and not config.get("import_clients"):
            result.message = "Nothing to import: both UniFi devices and clients are turned off"
            return result
        base, sites = self._connect(config)
        sites = self._selected_sites(config, sites)
        overwrite = bool(config.get("overwrite"))
        counts = {"devices": 0, "clients": 0, "no_name": 0, "filtered": 0}

        for site in sites:
            site_id = _text(site.get("id"))
            site_name = _text(site.get("name")) or _text(site.get("internalReference"))
            if not site_id:
                result.errors.append(f"site {site_name or '?'}: no id in the answer, skipped")
                continue
            if config.get("import_devices"):
                self._sync_devices(config, base, site_id, site_name, overwrite, result, counts)
            if config.get("import_clients"):
                self._sync_clients(config, base, site_id, site_name, overwrite, result, counts)

        parts = [f"{len(sites)} site{'' if len(sites) == 1 else 's'}"]
        if config.get("import_devices"):
            parts.append(f"{counts['devices']} UniFi devices")
        if config.get("import_clients"):
            parts.append(f"{counts['clients']} clients")
            if counts["no_name"]:
                parts.append(f"{counts['no_name']} clients without a name ignored")
        result.message = ", ".join(parts)
        return result

    @staticmethod
    def _count(result, action):
        if action == "created":
            result.created += 1
        elif action == "updated":
            result.updated += 1
        else:
            result.skipped += 1

    def _sync_devices(self, config, base, site_id, site_name, overwrite, result, counts):
        path = f"/sites/{site_id}/devices"
        try:
            for item in self._paged(config, base, path):
                label = item.get("name") or item.get("macAddress") or item.get("id") \
                    if isinstance(item, dict) else None
                try:
                    external_id, fields = self.map_device(item, site_name)
                    _, action = upsert_device(self.key, external_id, fields, overwrite=overwrite)
                except (ValueError, TypeError, AttributeError, KeyError) as exc:
                    result.errors.append(f"UniFi device {label or '?'} ({site_name}): {exc}")
                    continue
                counts["devices"] += 1
                self._count(result, action)
        except Truncated:
            result.errors.append(f"site {site_name}: stopped after {MAX_PAGES} pages of devices")

    def _sync_clients(self, config, base, site_id, site_name, overwrite, result, counts):
        path = f"/sites/{site_id}/clients"
        wired_only = bool(config.get("wired_clients_only", True))
        try:
            for item in self._paged(config, base, path):
                if not isinstance(item, dict):
                    result.errors.append(f"client ({site_name}): not a JSON object, skipped")
                    continue
                ctype = _text(item.get("type")).upper()
                # VPN and Teleport entries are connections, not devices.
                if ctype not in ("WIRED", "WIRELESS") or (wired_only and ctype != "WIRED"):
                    continue
                label = item.get("name") or item.get("macAddress") or item.get("id")
                try:
                    mapped = self.map_client(item, site_name)
                    if mapped is None:
                        counts["no_name"] += 1
                        continue
                    external_id, fields = mapped
                    _, action = upsert_device(self.key, external_id, fields, overwrite=overwrite)
                except (ValueError, TypeError, AttributeError, KeyError) as exc:
                    result.errors.append(f"client {label or '?'} ({site_name}): {exc}")
                    continue
                counts["clients"] += 1
                self._count(result, action)
        except Truncated:
            result.errors.append(f"site {site_name}: stopped after {MAX_PAGES} pages of clients")

    # --- mapping ----------------------------------------------------------
    @staticmethod
    def map_device(item, site_name):
        """Return (external_id, fields) for one adopted UniFi device."""
        if not isinstance(item, dict):
            raise ValueError("not a JSON object")
        mac = normalize_mac(item.get("macAddress") or item.get("mac"))
        model = _text(item.get("model"))
        name = _text(item.get("name"))
        if not name:
            if not mac:
                raise ValueError("no name and no MAC address")
            suffix = mac.replace(":", "")[-6:]
            name = f"{model}-{suffix}" if model else f"unifi-{suffix}"
        device_id = _text(item.get("id"))
        if device_id:
            external_id = f"device:{device_id}"
        elif mac:
            external_id = f"device:{mac}"
        else:
            raise ValueError("no id and no MAC address")
        fields = {
            "hostname": name,
            "mac_address": mac or "",
            "ip_address": _text(item.get("ipAddress")),
            "device_type": device_type_for(item.get("features")),
            "operating_system": f"UniFi ({model})" if model else "UniFi",
            "os_version": _text(item.get("firmwareVersion")),
            "location": site_name,
        }
        return external_id, fields

    @staticmethod
    def map_client(item, site_name):
        """Return (external_id, fields) for one client, or None when it has no usable name."""
        if not isinstance(item, dict):
            raise ValueError("not a JSON object")
        mac = normalize_mac(item.get("macAddress") or item.get("mac"))
        if not mac:
            raise ValueError("no MAC address")
        name = ""
        for key in ("name", "hostname"):
            candidate = _text(item.get(key))
            # UniFi shows the MAC as the name of a client it knows nothing about: that is not
            # a name, and a device list full of MAC addresses helps nobody.
            if candidate and normalize_mac(candidate) != mac:
                name = candidate
                break
        if not name:
            return None
        fields = {
            "hostname": name,
            "mac_address": mac,
            "ip_address": _text(item.get("ipAddress")),
            "location": site_name,
        }
        return f"client:{mac}", fields


INTEGRATION = UniFiNetwork()
