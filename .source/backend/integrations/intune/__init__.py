"""Microsoft Intune: one-way import of managed devices through Microsoft Graph.

Uses an Entra ID app registration with the client credentials flow (application
permission DeviceManagementManagedDevices.Read.All) and plain ``requests``. Global
Microsoft cloud endpoints only.
"""
import re
import time
from urllib.parse import urlparse

import requests

from backend.integrations import Field, Integration, IntegrationError, SyncResult
from backend.integrations.devices import normalize_mac, upsert_device

LOGIN_HOST = "https://login.microsoftonline.com"
GRAPH_HOST = "graph.microsoft.com"
DEVICES_URL = f"https://{GRAPH_HOST}/v1.0/deviceManagement/managedDevices"
SCOPE = f"https://{GRAPH_HOST}/.default"
PERMISSION = "DeviceManagementManagedDevices.Read.All"

TIMEOUT = 30
PAGE_SIZE = 200
MAX_PAGES = 250            # 50,000 devices, far beyond any tenant this is meant for
MAX_SHORT_RETRY = 5        # seconds: a Retry-After this short is waited out once

SELECT = ",".join([
    "id", "deviceName", "operatingSystem", "osVersion", "serialNumber", "model",
    "manufacturer", "wiFiMacAddress", "ethernetMacAddress", "managedDeviceOwnerType",
    "lastSyncDateTime",
])

_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_DOMAIN = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)

# AADSTS codes from the token endpoint's "error_codes" list, mapped to what the admin should do.
# Source: Microsoft Entra authentication and authorization error codes (learn.microsoft.com).
_AADSTS_MESSAGES = {
    90002: "Tenant not found. Check the Tenant ID (the Directory (tenant) ID of your Entra tenant).",
    700016: "Application (client) ID not found in this tenant. Check the Application (client) ID "
            "and that the app registration lives in the same tenant as the Tenant ID.",
    7000215: "Client secret rejected. Paste the secret Value, not the Secret ID, and check that "
             "the secret still exists on the app registration.",
    7000222: "The client secret has expired. Create a new client secret on the app registration "
             "under Certificates & secrets and save it here.",
    7000112: "The app registration is disabled in this tenant. Enable it in Entra ID.",
}

# Values Intune reports when the firmware has no real serial number. Treated as empty so
# unrelated devices are never matched together on serial.
_PLACEHOLDER_SERIALS = {
    "", "0", "none", "null", "n/a", "na", "unknown", "default string", "default",
    "to be filled by o.e.m.", "to be filled by oem", "o.e.m.", "oem", "systemserialnumber",
    "system serial number", "chassis serial number", "not specified", "not applicable",
    "invalid", "serial", "123456789", "0123456789", "1234567890", "none provided",
}

OS_CHOICES = [
    ("all", "All"),
    ("windows", "Windows only"),
    ("macos", "macOS only"),
    ("windows_macos", "Windows and macOS"),
    ("mobile", "Mobile only (iOS/iPadOS and Android)"),
]


def _os_family(operating_system):
    os_name = (operating_system or "").strip().lower()
    if os_name.startswith("windows"):
        return "windows"
    if os_name.startswith("mac"):
        return "macos"
    if os_name in ("ios", "ipados"):
        return "apple_mobile"
    if os_name.startswith("android"):
        return "android"
    if os_name == "linux" or os_name.startswith("linux"):
        return "linux"
    return "other"


def os_selected(operating_system, choice):
    family = _os_family(operating_system)
    if choice == "windows":
        return family == "windows"
    if choice == "macos":
        return family == "macos"
    if choice == "windows_macos":
        return family in ("windows", "macos")
    if choice == "mobile":
        return family in ("apple_mobile", "android")
    return True


def clean_serial(value):
    serial = " ".join(str(value or "").split())
    if serial.lower() in _PLACEHOLDER_SERIALS:
        return ""
    if set(serial) <= {"0"}:          # "0000000" and friends
        return ""
    return serial


def clean_mac(value):
    mac = normalize_mac(value)
    if not mac or mac == "00:00:00:00:00:00":
        return ""
    return mac


_VM_MODELS = ("virtual machine", "vmware", "virtualbox", "kvm", "qemu", "cloud pc", "parallels")
_MAC_DESKTOPS = ("imac", "macmini", "macpro", "macstudio")


def guess_device_type(operating_system, model):
    """PrivateGlue device type from what Intune v1.0 reports.

    Graph v1.0 has no chassis type, so laptop versus desktop is a guess for Windows. Mobile
    types come from the OS (and the model for iPads and Android tablets).
    """
    family = _os_family(operating_system)
    model_key = (model or "").lower()
    compact = model_key.replace(" ", "")
    if family == "apple_mobile":
        if (operating_system or "").strip().lower() == "ipados" or "ipad" in model_key:
            return "Tablet"
        return "Phone"
    if family == "android":
        if "tab" in model_key or "pad" in model_key or re.match(r"^sm-[tpx]\d", model_key):
            return "Tablet"
        return "Phone"
    if family in ("windows", "linux"):
        if any(word in model_key for word in _VM_MODELS):
            return "VM"
        return "Laptop"
    if family == "macos":
        if "macbook" in compact:
            return "Laptop"
        if any(word in compact for word in _MAC_DESKTOPS):
            return "Desktop"
        return "Laptop"
    return "Other"


def map_device(item, location=""):
    """Turn one managedDevice into (external_id, fields). Raises ValueError on unusable data."""
    if not isinstance(item, dict):
        raise ValueError("record is not an object")
    external_id = str(item.get("id") or "").strip()
    if not external_id:
        raise ValueError("record has no id")
    hostname = str(item.get("deviceName") or "").strip()
    if not hostname:
        raise ValueError("device has no name in Intune")
    mac = clean_mac(item.get("ethernetMacAddress")) or clean_mac(item.get("wiFiMacAddress"))
    fields = {
        "hostname": hostname,
        "serial_number": clean_serial(item.get("serialNumber")),
        "mac_address": mac,
        "operating_system": str(item.get("operatingSystem") or "").strip(),
        "os_version": str(item.get("osVersion") or "").strip(),
        "device_type": guess_device_type(item.get("operatingSystem"), item.get("model")),
        "location": (location or "").strip(),
    }
    return external_id, fields


def _validate(config):
    tenant = str(config.get("tenant_id") or "").strip()
    client_id = str(config.get("client_id") or "").strip()
    secret = str(config.get("client_secret") or "").strip()
    if not (_GUID.match(tenant) or _DOMAIN.match(tenant)):
        raise IntegrationError(
            "Tenant ID must be the Directory (tenant) ID (a GUID) or a domain such as contoso.onmicrosoft.com."
        )
    if not _GUID.match(client_id):
        raise IntegrationError("Application (client) ID must be a GUID, as shown on the app registration's Overview page.")
    if not secret:
        raise IntegrationError("Client secret is missing.")
    return tenant, client_id, secret


def _network_error(exc, what, timeout):
    if isinstance(exc, requests.exceptions.SSLError):
        return IntegrationError(
            f"Could not verify the TLS certificate of {what}. If a proxy inspects HTTPS traffic, "
            "give the container its CA certificate (REQUESTS_CA_BUNDLE)."
        )
    if isinstance(exc, requests.exceptions.ConnectionError):
        return IntegrationError(f"Could not connect to {what}. Check that this container can reach the internet.")
    if isinstance(exc, requests.exceptions.Timeout):
        return IntegrationError(f"{what} did not answer within {timeout} seconds.")
    return IntegrationError(f"Request to {what} failed: {type(exc).__name__}")


def get_token(config, session=None):
    """Client credentials flow. Returns the access token; never puts it or the secret in a message."""
    tenant, client_id, secret = _validate(config)
    http = session or requests
    what = "Microsoft Entra ID"
    url = f"{LOGIN_HOST}/{tenant}/oauth2/v2.0/token"
    try:
        resp = http.post(url, data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
            "scope": SCOPE,
        }, timeout=TIMEOUT)
    except requests.exceptions.RequestException as exc:
        raise _network_error(exc, what, TIMEOUT)

    try:
        body = resp.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        body = {}

    if resp.status_code >= 400:
        codes = body.get("error_codes") or []
        if not isinstance(codes, list):
            codes = []
        for code in codes:
            if code in _AADSTS_MESSAGES:
                raise IntegrationError(f"Sign-in failed (AADSTS{code}): {_AADSTS_MESSAGES[code]}")
        code_text = f"AADSTS{codes[0]}" if codes and isinstance(codes[0], int) else f"HTTP {resp.status_code}"
        error = body.get("error")
        error_text = f", {error}" if isinstance(error, str) and re.match(r"^[a-z_]{1,40}$", error) else ""
        raise IntegrationError(
            f"Microsoft Entra ID refused the sign-in ({code_text}{error_text}). "
            "Check the Tenant ID, Application (client) ID and client secret."
        )

    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        raise IntegrationError("Microsoft Entra ID answered without an access token.")
    return token


def _retry_after(resp):
    try:
        return max(0, int(str(resp.headers.get("Retry-After", "")).strip()))
    except ValueError:
        return None


def graph_get(url, token, params=None, session=None, sleep=time.sleep):
    """GET one Graph page. Only ever sends the bearer token to https://graph.microsoft.com."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != GRAPH_HOST:
        raise IntegrationError("Microsoft Graph returned a next-page link to another host. Stopped to protect the access token.")
    http = session or requests
    what = "Microsoft Graph"
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    for attempt in (1, 2):
        try:
            resp = http.get(url, headers=headers, params=params, timeout=TIMEOUT)
        except requests.exceptions.RequestException as exc:
            raise _network_error(exc, what, TIMEOUT)
        if resp.status_code == 429:
            wait = _retry_after(resp)
            if attempt == 1 and wait is not None and wait <= MAX_SHORT_RETRY:
                sleep(wait)
                continue
            later = f" Try again in {wait} seconds." if wait else " Try again later."
            raise IntegrationError("Microsoft Graph is throttling requests (HTTP 429)." + later)
        break

    if resp.status_code == 401:
        raise IntegrationError("Microsoft Graph rejected the access token (HTTP 401). Check the app registration and try again.")
    if resp.status_code == 403:
        raise IntegrationError(
            f"Microsoft Graph denied access (HTTP 403). The app registration needs the application "
            f"permission {PERMISSION} on Microsoft Graph with admin consent granted, and the "
            "tenant needs an active Intune license."
        )
    if resp.status_code >= 400:
        raise IntegrationError(f"Microsoft Graph answered with an error (HTTP {resp.status_code}).")
    try:
        data = resp.json()
    except ValueError:
        raise IntegrationError("Microsoft Graph did not return JSON.")
    if not isinstance(data, dict):
        raise IntegrationError("Microsoft Graph returned an unexpected answer.")
    return data


def list_devices(token, session=None, sleep=time.sleep):
    """All managed devices, following @odata.nextLink. Returns (devices, truncated)."""
    devices = []
    url, params = DEVICES_URL, {"$select": SELECT, "$top": str(PAGE_SIZE)}
    for _ in range(MAX_PAGES):
        data = graph_get(url, token, params=params, session=session, sleep=sleep)
        value = data.get("value")
        if not isinstance(value, list):
            raise IntegrationError("Microsoft Graph returned an unexpected answer (no device list).")
        devices.extend(value)
        url = data.get("@odata.nextLink")
        if not url:
            return devices, False
        params = None  # the next link already carries the query
    return devices, True


class Intune(Integration):
    key = "intune"
    name = "Microsoft Intune"
    description = "Imports Intune managed devices (Windows, macOS, iOS/iPadOS, Android) through Microsoft Graph."
    icon = "microsoft"
    fields = [
        Field("tenant_id", "Tenant ID", required=True,
              placeholder="00000000-0000-0000-0000-000000000000",
              help="Directory (tenant) ID from the app registration's Overview page, or your onmicrosoft.com domain."),
        Field("client_id", "Application (client) ID", required=True,
              placeholder="00000000-0000-0000-0000-000000000000",
              help="From the app registration's Overview page."),
        Field("client_secret", "Client secret", kind="password", required=True,
              help="The secret Value (not the Secret ID). It expires: renew it before the date shown in Entra."),
        Field("os_filter", "Operating systems to import", kind="select", default="all", choices=OS_CHOICES),
        Field("skip_personal", "Skip personally owned devices", kind="checkbox", default=False,
              help="Leave out devices Intune marks as personal (BYOD)."),
        Field("location", "Location label for imported devices",
              placeholder="Office", help="Optional. Filled in on imported devices that have no location yet."),
        Field("overwrite", "Overwrite PrivateGlue values", kind="checkbox", default=False,
              help="Off: only empty fields are filled in. On: Intune wins for name, serial, MAC, OS and location. "
                   "The device type is never overwritten."),
    ]

    def test(self, config):
        token = get_token(config)
        graph_get(DEVICES_URL, token, params={"$select": "id", "$top": "1"})
        tenant = str(config.get("tenant_id") or "").strip()
        return f"Connected to tenant {tenant}, permission OK"

    def sync(self, config, session=None, sleep=time.sleep):
        token = get_token(config, session=session)
        devices, truncated = list_devices(token, session=session, sleep=sleep)
        result = SyncResult()
        if truncated:
            result.errors.append(
                f"Stopped after {MAX_PAGES} pages ({len(devices)} devices). The rest was not imported."
            )

        choice = config.get("os_filter") or "all"
        skip_personal = bool(config.get("skip_personal"))
        overwrite = bool(config.get("overwrite"))
        location = config.get("location") or ""
        filtered = 0

        # Oldest check-in first: when Intune keeps a stale record next to a re-enrolled one with
        # the same serial, the most recent record is applied last.
        def last_sync(item):
            return str(item.get("lastSyncDateTime") or "") if isinstance(item, dict) else ""

        for item in sorted(devices, key=last_sync):
            if isinstance(item, dict):
                if not os_selected(item.get("operatingSystem"), choice):
                    filtered += 1
                    continue
                if skip_personal and str(item.get("managedDeviceOwnerType") or "").lower() == "personal":
                    filtered += 1
                    continue
            try:
                external_id, fields = map_device(item, location)
                device_type = fields.pop("device_type")
                device, action = upsert_device(self.key, external_id, fields, overwrite=overwrite)
            except ValueError as exc:
                ref = item.get("id") if isinstance(item, dict) else None
                label = (item.get("deviceName") if isinstance(item, dict) else None) or ref or "unknown device"
                result.errors.append(f"{label}: {exc}")
                continue
            # The type is a guess for computers, so it only fills an empty type and a manual
            # correction is never overwritten, not even with "Overwrite" on.
            if device_type and not device.device_type:
                device.device_type = device_type
                if action == "unchanged":
                    action = "updated"
            if action == "created":
                result.created += 1
            elif action == "updated":
                result.updated += 1
            else:
                result.skipped += 1

        if filtered:
            result.message = f"{filtered} devices left out by the filters"
        return result


INTEGRATION = Intune()
