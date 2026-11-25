"""UniFi Network: import gateways, switches, access points and (optionally) clients.

Two ways to sign in, because not every UniFi set-up offers both:

* API key. The official UniFi Network API (the "Integration API"), with a key created in
  UniFi Network under Settings > Control Plane > Integrations and sent in the X-API-KEY
  header. Only UniFi OS has it: Cloud Gateways, UDM, UCG, Cloud Key and UniFi OS Server.
  It lives under /proxy/network/integration/v1 (or /integration/v1).

* Username and password. The classic controller API that every UniFi Network has, including
  the self-hosted "UniFi Network Server", which cannot create API keys at all. PrivateGlue
  signs in with a local account, reads, and signs out again. A view-only account is enough.

Read-only either way: apart from signing in and out, only GET requests are made.
"""
from urllib.parse import urlsplit

import requests

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

AUTH_API_KEY = "api_key"
AUTH_LOGIN = "login"

# Classic API: the device "type" says what a device is.
_CLASSIC_FEATURES = {
    "ugw": ["gateway"], "udm": ["gateway"], "uxg": ["gateway"], "ucg": ["gateway"],
    "uap": ["accessPoint"], "usw": ["switching"],
}
_BAD_LOGIN = ("UniFi did not accept this username and password. Use a local account (not your "
              "UI.com account), without two-factor sign-in.")


class ClassicSession:
    """One signed-in visit to the classic controller API, on UniFi OS or a Network Server."""

    def __init__(self, url, username, password, verify):
        self.url, self.verify = url, verify
        self.http = requests.Session()
        self.csrf = ""
        self.unifi_os = self._looks_like_unifi_os()
        try:
            self._login(username, password)
        except IntegrationError as exc:
            if "404" not in str(exc):
                raise
            # Guessed the wrong kind of server: try the other sign-in address once.
            self.unifi_os = not self.unifi_os
            try:
                self._login(username, password)
            except IntegrationError as second:
                if "404" in str(second):
                    raise IntegrationError("No UniFi sign-in page found at this address (HTTP 404). "
                                           "Check the console address and port.") from second
                raise

    def _looks_like_unifi_os(self):
        """A UniFi OS console answers its front page directly; a Network Server redirects to
        /manage. Only a first guess: a wrong one is corrected when signing in."""
        try:
            resp = self.http.request("GET", self.url + "/", verify=self.verify, timeout=10,
                                     allow_redirects=False)
            return resp.status_code == 200
        except requests.exceptions.RequestException:
            return True  # the sign-in request reports the real problem in plain words

    @property
    def prefix(self):
        return "/proxy/network" if self.unifi_os else ""

    def _login(self, username, password):
        path = "/api/auth/login" if self.unifi_os else "/api/login"
        body = {"username": username, "password": password}
        try:
            resp = request_json("POST", self.url + path, json=body, verify=self.verify,
                                session=_CsrfCapture(self), what=WHAT)
        except IntegrationError as exc:
            text = str(exc)
            if "HTTP 499" in text:
                raise IntegrationError("This UniFi account asks for a two-factor code. Use a local "
                                       "account without two-factor sign-in.") from exc
            if "HTTP 429" in text:
                raise IntegrationError("UniFi is refusing sign-ins for a moment after too many "
                                       "attempts. Wait a few minutes and try again.") from exc
            if "HTTP 400" in text or "HTTP 401" in text or "HTTP 403" in text:
                raise IntegrationError(_BAD_LOGIN) from exc
            raise
        if isinstance(resp, dict) and (resp.get("meta") or {}).get("rc") == "error":
            raise IntegrationError(_BAD_LOGIN)

    def get(self, path):
        """The "data" list of one classic API call."""
        answer = request_json("GET", self.url + self.prefix + path, verify=self.verify,
                              session=self.http, what=WHAT)
        if not isinstance(answer, dict) or not isinstance(answer.get("data"), list):
            raise IntegrationError(f"{WHAT} returned an unexpected answer for {path}.")
        if (answer.get("meta") or {}).get("rc") == "error":
            raise IntegrationError(f"{WHAT} refused {path}. The account may lack access to this site.")
        return answer["data"]

    def close(self):
        """Sign out, so no session stays open on the console. Never an error for the user."""
        path = "/api/auth/logout" if self.unifi_os else "/api/logout"
        try:
            self.http.request("POST", self.url + path, verify=self.verify, timeout=10,
                              headers={"X-CSRF-Token": self.csrf} if self.csrf else None)
        except requests.exceptions.RequestException:
            pass
        self.http.close()


class _CsrfCapture:
    """Passes a request to the session and keeps the CSRF token UniFi OS hands out at
    sign-in. It is needed to sign out again."""

    def __init__(self, owner):
        self.owner = owner

    def request(self, method, url, **kwargs):
        resp = self.owner.http.request(method, url, **kwargs)
        headers = getattr(resp, "headers", None) or {}
        self.owner.csrf = headers.get("X-CSRF-Token") or headers.get("X-Updated-CSRF-Token") or self.owner.csrf
        return resp


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
        Field("auth", "Sign in with", kind="select", default=AUTH_API_KEY,
              choices=[(AUTH_API_KEY, "API key (UniFi OS: Cloud Gateway, UDM, Cloud Key, UniFi OS Server)"),
                       (AUTH_LOGIN, "Username and password (works everywhere, needed for a self-hosted Network Server)")],
              help="A self-hosted UniFi Network Server cannot create API keys: choose username and password there."),
        Field("api_key", "API key", kind="password", show_if=("auth", AUTH_API_KEY),
              help="Create it in UniFi Network under Settings > Control Plane > Integrations."),
        Field("username", "Username", kind="text", default="", show_if=("auth", AUTH_LOGIN),
              help="A local account made for PrivateGlue. View-only is enough."),
        Field("password", "Password", kind="password", show_if=("auth", AUTH_LOGIN),
              help="Not your UI.com password: that account asks for a two-factor code."),
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

    # --- sign-in method ---------------------------------------------------
    @staticmethod
    def _uses_login(config):
        """The chosen way of signing in. When what it needs is missing and the other way is
        filled in completely, that one is used: somebody who typed a username and password and
        left the choice on "API key" plainly means to sign in with those."""
        has_key = bool(config.get("api_key"))
        has_login = bool(_text(config.get("username")) and config.get("password"))
        if _text(config.get("auth")) == AUTH_LOGIN:
            return has_login or not has_key
        return has_login and not has_key

    def _check_credentials(self, config):
        """Say which field is missing for the chosen way of signing in."""
        if self._uses_login(config):
            if not _text(config.get("username")) or not config.get("password"):
                raise IntegrationError("Fill in the username and the password, or switch "
                                       '"Sign in with" to API key.')
        elif not config.get("api_key"):
            raise IntegrationError('Fill in the API key. If your UniFi cannot create one (a self-hosted '
                                   'Network Server cannot), switch "Sign in with" to username and password.')

    def _open_classic(self, config):
        return ClassicSession(self._base_url(config), _text(config.get("username")),
                              config.get("password") or "", bool(config.get("verify_tls", True)))

    @staticmethod
    def _classic_sites(session):
        """Sites in the shape the rest of the module uses."""
        return [{"id": _text(s.get("name")), "internalReference": _text(s.get("name")),
                 "name": _text(s.get("desc")) or _text(s.get("name"))}
                for s in session.get("/api/self/sites") if isinstance(s, dict) and _text(s.get("name"))]

    @staticmethod
    def classic_device(item):
        """A device of the classic API in the shape map_device expects. None: not adopted."""
        if not isinstance(item, dict):
            return item
        if item.get("adopted") is False:
            return None
        return {"macAddress": item.get("mac"), "name": item.get("name"), "ipAddress": item.get("ip"),
                "model": item.get("model"), "firmwareVersion": item.get("version"),
                "features": _CLASSIC_FEATURES.get(_text(item.get("type")).lower(), [])}

    @staticmethod
    def classic_client(item):
        """A client of the classic API in the shape map_client expects."""
        if not isinstance(item, dict):
            return item
        return {"type": "WIRED" if item.get("is_wired") else "WIRELESS", "macAddress": item.get("mac"),
                "name": item.get("name"), "hostname": item.get("hostname"), "ipAddress": item.get("ip")}

    def _test_classic(self, config):
        session = self._open_classic(config)
        try:
            sites = self._classic_sites(session)
            selected = self._selected_sites(config, sites)
            version = ""
            if selected:
                try:
                    info = session.get(f"/api/s/{selected[0]['id']}/stat/sysinfo")
                    version = _text(info[0].get("version")) if info and isinstance(info[0], dict) else ""
                except IntegrationError:
                    pass  # the sites call already proved the sign-in works
        finally:
            session.close()
        prefix = f"Connected to UniFi Network {version}" if version else "Connected"
        count = len(sites)
        text = f"{prefix}, {count} site{'' if count == 1 else 's'} found"
        if _text(config.get("site_name")):
            text += f', importing site "{_text(selected[0].get("name"))}"'
        return text

    def _sync_classic(self, config, result, counts):
        overwrite = bool(config.get("overwrite"))
        wired_only = bool(config.get("wired_clients_only", True))
        session = self._open_classic(config)
        try:
            sites = self._selected_sites(config, self._classic_sites(session))
            for site in sites:
                site_id, site_name = site["id"], site["name"]
                if config.get("import_devices"):
                    for raw in session.get(f"/api/s/{site_id}/stat/device"):
                        item = self.classic_device(raw)
                        if item is None:
                            continue
                        label = (raw.get("name") or raw.get("mac")) if isinstance(raw, dict) else None
                        try:
                            external_id, fields = self.map_device(item, site_name)
                            _, action = upsert_device(self.key, external_id, fields, overwrite=overwrite)
                        except (ValueError, TypeError, AttributeError, KeyError) as exc:
                            result.errors.append(f"UniFi device {label or '?'} ({site_name}): {exc}")
                            continue
                        counts["devices"] += 1
                        self._count(result, action)
                if config.get("import_clients"):
                    for raw in session.get(f"/api/s/{site_id}/stat/sta"):
                        item = self.classic_client(raw)
                        if not isinstance(item, dict):
                            result.errors.append(f"client ({site_name}): not a JSON object, skipped")
                            continue
                        if wired_only and item["type"] != "WIRED":
                            continue
                        try:
                            mapped = self.map_client(item, site_name)
                            if mapped is None:
                                counts["no_name"] += 1
                                continue
                            external_id, fields = mapped
                            _, action = upsert_device(self.key, external_id, fields, overwrite=overwrite)
                        except (ValueError, TypeError, AttributeError, KeyError) as exc:
                            result.errors.append(f"client {item.get('name') or item.get('macAddress') or '?'} ({site_name}): {exc}")
                            continue
                        counts["clients"] += 1
                        self._count(result, action)
        finally:
            session.close()
        return sites

    # --- test -------------------------------------------------------------
    def test(self, config):
        self._check_credentials(config)
        if self._uses_login(config):
            return self._test_classic(config)
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
        self._check_credentials(config)
        counts = {"devices": 0, "clients": 0, "no_name": 0, "filtered": 0}
        if self._uses_login(config):
            sites = self._sync_classic(config, result, counts)
        else:
            sites = self._sync_api_key(config, result, counts)

        parts = [f"{len(sites)} site{'' if len(sites) == 1 else 's'}"]
        if config.get("import_devices"):
            parts.append(f"{counts['devices']} UniFi devices")
        if config.get("import_clients"):
            parts.append(f"{counts['clients']} clients")
            if counts["no_name"]:
                parts.append(f"{counts['no_name']} clients without a name ignored")
        result.message = ", ".join(parts)
        return result

    def _sync_api_key(self, config, result, counts):
        base, sites = self._connect(config)
        sites = self._selected_sites(config, sites)
        overwrite = bool(config.get("overwrite"))
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
        return sites

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
