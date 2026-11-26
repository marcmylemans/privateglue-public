"""Address: where a credential is used, such as https://10.0.10.11:8006.

The address is typed by people and shown as a link, so one helper, ``openable()``, decides
whether a value may ever become an href. Every template asks it; nothing else builds a link.
"""
import re

from backend.features import Feature

MAX_LENGTH = 500
#: The only schemes that become a link. Anything else (javascript:, data:, file:, ...) is text.
OPEN_SCHEMES = ("https", "http", "ssh", "rdp")
WEB_SCHEMES = ("https", "http")

_SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):")
# "host:port" or "host:port/path": the part before the colon is a host, not a scheme.
_HOST_PORT = re.compile(r"^[^/:?#@]+:\d+(?:[/?#]|$)")
_BAD_CHARS = re.compile(r"[\s\x00-\x1f\x7f]")
# What may go into a copied "ssh user@ip" command: nothing a shell would act on.
_SAFE_SSH_USER = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._\-]*$")
_SAFE_IP = re.compile(r"^[0-9A-Fa-f:.]+$")


def scheme(value):
    """The scheme of an address in lower case ("https"), or None when it has none."""
    text = (value or "").strip()
    if not text or _HOST_PORT.match(text):
        return None
    match = _SCHEME.match(text)
    return match.group(1).lower() if match else None


def openable(value):
    """True only when the address may be used as an href: an allowed scheme and no
    whitespace or control characters anywhere (browsers skip those inside a scheme)."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or len(text) > MAX_LENGTH or _BAD_CHARS.search(text):
        return False
    return scheme(text) in OPEN_SCHEMES


def normalise(value):
    """Trim, and give an address without a scheme https:// in front of it."""
    text = (value or "").strip()
    if not text:
        return ""
    if text.startswith("//"):
        return "https:" + text
    if scheme(text) is None and (text[0].isalnum() or text[0] == "["):
        return "https://" + text
    return text


def problem(value):
    """A message when the address cannot be stored, otherwise None."""
    text = (value or "").strip()
    if len(text) > MAX_LENGTH:
        return f"The address is too long. Keep it under {MAX_LENGTH} characters."
    if _BAD_CHARS.search(text):
        return "The address cannot contain spaces, tabs or line breaks."
    return None


def short(value):
    """The address for a narrow column: https:// is left out, it is the usual case."""
    text = (value or "").strip()
    return text[8:] if text.lower().startswith("https://") else text


def _is_proxmox(device):
    return "proxmox" in (device.operating_system or "").lower()


def suggestions_for(device):
    """Addresses worth offering for a device, from its IP address."""
    ip = (device.ip_address or "").strip()
    if not ip or not _SAFE_IP.match(ip):
        return []
    host = f"[{ip}]" if ":" in ip else ip
    if _is_proxmox(device):
        return [f"https://{host}:8006", f"ssh://{host}"]
    return [f"https://{host}", f"ssh://{host}"]


def _by_title(credentials):
    return sorted(credentials, key=lambda c: ((c.title or "").lower(), c.id or 0))


def _ssh_user(username):
    name = (username or "").strip()
    if "@" in name:
        name = name.split("@", 1)[0]  # root@pam is the Proxmox realm, not part of the login
    return name if _SAFE_SSH_USER.match(name) else ""


class Address(Feature):
    key = "address"
    name = "Address"
    order = 10
    columns = {"credential": {"address": "TEXT"}}

    # --- helpers for templates (feat.address....) --------------------------------------
    open_schemes = OPEN_SCHEMES

    def openable(self, value):
        return openable(value)

    def short(self, value):
        return short(value)

    def suggestions(self, devices, selected_ids=None):
        """[(device_id, [address, ...]), ...] for devices that have an IP address."""
        wanted = None if selected_ids is None else {int(i) for i in selected_ids}
        out = []
        for device in devices or []:
            if wanted is not None and device.id not in wanted:
                continue
            found = suggestions_for(device)
            if found:
                out.append((device.id, found))
        return out

    def web_credential(self, credentials):
        """The first credential, by title, whose address opens in a browser."""
        for cred in _by_title(credentials or []):
            if openable(cred.address) and scheme(cred.address) in WEB_SCHEMES:
                return cred
        return None

    def ssh_command(self, device, credentials):
        """"ssh user@ip" for the copy button, or None when the device has no usable IP."""
        ip = (device.ip_address or "").strip()
        if not ip or not _SAFE_IP.match(ip):
            return None
        for cred in _by_title(credentials or []):
            user = _ssh_user(cred.username)
            if user:
                return f"ssh {user}@{ip}"
        return f"ssh {ip}"

    # --- hooks -------------------------------------------------------------------------
    def credential_validate(self, form, credential):
        message = problem(form.get("address"))
        return [message] if message else []

    def credential_saved(self, credential, form, created, password_changed, old_password):
        if "address" not in form:  # a save that did not come from the form keeps the value
            return
        credential.address = normalise(form.get("address")) or None


FEATURE = Address()
