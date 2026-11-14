"""Proxmox VE: one-way import of cluster nodes, QEMU virtual machines and LXC containers.

Talks to the Proxmox VE REST API (https://<host>:8006/api2/json) with an API token, through the
framework's ``request_json`` so every failure reads the same way and every call has a timeout.
Read only: this module only sends GET requests.

This is separate from the older "Fetch info" button on a device page
(``backend/utils/proxmox.py``), which uses a stored credential and proxmoxer.
"""
import ipaddress
import re
from urllib.parse import quote

import requests

from backend.integrations import Field, Integration, IntegrationError, SyncResult
from backend.integrations.devices import upsert_device
from backend.integrations.http import request_json

# Call timeouts in seconds. Guest agent calls get a shorter one: a hanging agent must not
# stall the whole run.
TIMEOUT = 20
AGENT_TIMEOUT = 8
# Proxmox has no paging: /cluster/resources returns everything in one answer. This cap only
# protects against a runaway answer.
MAX_RESOURCES = 10000

NODE_TYPE = "Server"
GUEST_TYPE = "VM"  # used for both QEMU VMs and LXC containers, see the docs for why

# QEMU "ostype" values (Proxmox VE API, /nodes/{node}/qemu/{vmid}/config) to readable names.
QEMU_OSTYPES = {
    "wxp": "Windows XP",
    "w2k": "Windows 2000",
    "w2k3": "Windows Server 2003",
    "w2k8": "Windows Server 2008",
    "wvista": "Windows Vista",
    "win7": "Windows 7",
    "win8": "Windows 8",
    "win10": "Windows 10",
    "win11": "Windows 11",
    "l24": "Linux",
    "l26": "Linux",
    "solaris": "Solaris",
    # "other" means unspecified: left empty on purpose.
}
# LXC "ostype" values to readable names. "unmanaged" is left empty.
LXC_OSTYPES = {
    "debian": "Debian",
    "devuan": "Devuan",
    "ubuntu": "Ubuntu",
    "centos": "CentOS",
    "fedora": "Fedora",
    "opensuse": "openSUSE",
    "archlinux": "Arch Linux",
    "alpine": "Alpine Linux",
    "gentoo": "Gentoo",
    "nixos": "NixOS",
}
# NIC model names that QEMU uses as the key of the MAC address in net0 ("virtio=AA:BB:...").
QEMU_NIC_MODELS = {
    "e1000", "e1000-82540em", "e1000-82544gc", "e1000-82545em", "e1000e", "i82551",
    "i82557b", "i82559er", "ne2k_isa", "ne2k_pci", "pcnet", "rtl8139", "virtio", "vmxnet3",
}

_HOST_LABEL = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
# user@realm!tokenname. Proxmox token names start with a letter.
_TOKEN_ID = re.compile(r"^[^\s@!:=]+@[^\s@!:=]+![A-Za-z][A-Za-z0-9._-]*$")
_MAC = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")


# --- small helpers (module level so tests can use them directly) ---------------------------

def clean_host(value):
    """Return the host as it goes into a URL, or raise IntegrationError.

    Accepts a host name or an IPv4/IPv6 address only: no scheme, port, path or credentials.
    """
    host = (value or "").strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if not host:
        raise IntegrationError("Enter the host name or IP address of a Proxmox VE node.")
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None
    if addr is not None:
        return f"[{addr.compressed}]" if addr.version == 6 else addr.compressed
    name = host.rstrip(".")
    if len(name) > 253 or not all(_HOST_LABEL.match(label) for label in name.split(".")):
        raise IntegrationError(
            "The host must be a host name or IP address only, without https://, a port, "
            "a path or a user name (for example pve1.lan or 192.168.1.10)."
        )
    return name


def clean_port(value):
    try:
        port = int(value)
    except (TypeError, ValueError):
        port = 0
    if not 1 <= port <= 65535:
        raise IntegrationError("The port must be a number between 1 and 65535 (Proxmox VE uses 8006).")
    return port


def parse_kv(value):
    """Split a Proxmox property string such as "virtio=BC:24:11:AA:BB:CC,bridge=vmbr0"."""
    out = {}
    for part in str(value or "").split(","):
        if "=" in part:
            key, _, val = part.partition("=")
            out[key.strip()] = val.strip()
        elif part.strip():
            out.setdefault("_", part.strip())
    return out


def qemu_mac(net):
    """MAC address from a QEMU netX value, or None."""
    for key, val in parse_kv(net).items():
        if (key in QEMU_NIC_MODELS or key == "macaddr") and _MAC.match(val):
            return val
    return None


def lxc_net(net):
    """(mac, static IPv4) from an LXC netX value. The IP is None for dhcp/manual/missing."""
    kv = parse_kv(net)
    mac = kv.get("hwaddr") if _MAC.match(kv.get("hwaddr", "")) else None
    ip = kv.get("ip", "")
    ip = ip.split("/")[0] if ip and ip not in ("dhcp", "manual") else None
    return mac, (ip if usable_ipv4(ip) else None)


def usable_ipv4(value):
    """True for an IPv4 address that is not loopback, link-local or unspecified."""
    try:
        addr = ipaddress.ip_address(str(value or "").split("/")[0])
    except ValueError:
        return False
    return (addr.version == 4 and not addr.is_loopback and not addr.is_link_local
            and not addr.is_unspecified)


def first_ipv4(interfaces):
    """First usable IPv4 from a guest agent or LXC interfaces list."""
    for iface in interfaces or []:
        if not isinstance(iface, dict) or iface.get("name") == "lo":
            continue
        for item in iface.get("ip-addresses") or []:
            if not isinstance(item, dict):
                continue
            # The type is "ipv4" from the guest agent and "inet" from LXC: usable_ipv4 checks
            # the address itself, so the label does not matter.
            ip = item.get("ip-address")
            if usable_ipv4(ip):
                return str(ip).split("/")[0]
        inet = iface.get("inet")  # older LXC answers only carry "inet": "10.0.0.5/24"
        if usable_ipv4(inet):
            return inet.split("/")[0]
    return None


def agent_enabled(value):
    """The QEMU "agent" option is "1", "0" or "enabled=1,fstrim_cloned_disks=1"."""
    kv = parse_kv(value)
    flag = kv.get("enabled", kv.get("_", "0"))
    return str(flag).strip().lower() in ("1", "yes", "on", "true")


class _Api:
    """A thin GET-only client for the Proxmox VE API."""

    def __init__(self, config):
        self.host = clean_host(config.get("host"))
        self.port = clean_port(config.get("port") or 8006)
        token_id = (config.get("api_id") or "").strip()
        secret = (config.get("token_secret") or "").strip()
        if not _TOKEN_ID.match(token_id):
            raise IntegrationError(
                "The API token ID must look like user@realm!tokenname, for example "
                "privateglue@pve!import."
            )
        if not secret or any(c.isspace() for c in secret):
            raise IntegrationError("Enter the API token secret (shown once when the token was created).")
        self.verify = bool(config.get("verify_tls", True))
        self.base = f"https://{self.host}:{self.port}"
        self.what = f"Proxmox VE at {self.host}:{self.port}"
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"PVEAPIToken={token_id}={secret}"

    def get(self, path, params=None, timeout=TIMEOUT):
        body = request_json("GET", f"{self.base}/api2/json{path}", params=params,
                            verify=self.verify, timeout=timeout, session=self.session,
                            what=self.what)
        if not isinstance(body, dict) or "data" not in body:
            raise IntegrationError(f"{self.what} returned an unexpected answer for {path}.")
        return body["data"]

    def ui_url(self, resource_id):
        """Deep link into the web UI, e.g. https://pve1:8006/#v1:0:=qemu%2F100"""
        return f"{self.base}/#v1:0:={quote(resource_id, safe='')}"


def _seg(value):
    return quote(str(value), safe="")


class ProxmoxIntegration(Integration):
    key = "proxmox"
    name = "Proxmox VE"
    description = "Import the nodes, virtual machines and containers of a Proxmox VE cluster or single host."
    icon = "boxes"
    docs = "proxmox.md"
    fields = [
        Field("host", "Host", required=True, placeholder="pve1.lan or 192.168.1.10",
              help="Host name or IP address of any node in the cluster. No https:// and no port."),
        Field("port", "Port", kind="number", default=8006),
        Field("api_id", "API token ID", required=True, placeholder="privateglue@pve!import",
              help="In the form user@realm!tokenname. Create it under Datacenter > Permissions > API Tokens."),
        Field("token_secret", "API token secret", kind="password", required=True),
        Field("verify_tls", "Verify the TLS certificate", kind="checkbox", default=True,
              help="A default Proxmox VE install uses a self-signed certificate. Turn this off "
                   "for that, or install a trusted certificate on the node."),
        Field("import_nodes", "Import nodes", kind="checkbox", default=True),
        Field("import_vms", "Import virtual machines", kind="checkbox", default=True),
        Field("import_containers", "Import containers", kind="checkbox", default=True),
        Field("skip_templates", "Skip templates", kind="checkbox", default=True),
        Field("only_running", "Only running guests", kind="checkbox", default=False,
              help="Skip virtual machines and containers that are not running."),
        Field("location", "Location for imported devices", placeholder="Homelab rack",
              help="Optional. Put on every imported device."),
        Field("overwrite", "Overwrite PrivateGlue values", kind="checkbox", default=False,
              help="Off: only empty fields are filled in, your own edits stay. "
                   "On: Proxmox VE values replace what is in PrivateGlue."),
    ]

    # --- test ------------------------------------------------------------------------------
    def test(self, config):
        api = _Api(config)
        version = api.get("/version") or {}
        resources = api.get("/cluster/resources", params={"type": "node"}) or []
        nodes = [r for r in resources if isinstance(r, dict) and r.get("type") == "node"]
        if not nodes:
            raise IntegrationError(_NO_ACCESS)
        count = len(nodes)
        release = version.get("version") or version.get("release") if isinstance(version, dict) else None
        product = f"Proxmox VE {release}" if release else "Proxmox VE"
        return f"Connected to {product}, {count} node{'s' if count != 1 else ''}"

    # --- sync ------------------------------------------------------------------------------
    def sync(self, config):
        api = _Api(config)
        result = SyncResult()
        resources = api.get("/cluster/resources") or []
        if not isinstance(resources, list):
            raise IntegrationError(f"{api.what} returned an unexpected resource list.")
        if len(resources) > MAX_RESOURCES:
            result.errors.append(f"More than {MAX_RESOURCES} resources: only the first {MAX_RESOURCES} were read.")
            resources = resources[:MAX_RESOURCES]
        resources = [r for r in resources if isinstance(r, dict)]
        if not any(r.get("type") in ("node", "qemu", "lxc") for r in resources):
            raise IntegrationError(_NO_ACCESS)

        location = (config.get("location") or "").strip()
        overwrite = bool(config.get("overwrite"))
        counts = {"node": 0, "qemu": 0, "lxc": 0}

        def save(external_id, fields, url, label):
            if location:
                fields["location"] = location
            try:
                _, action = upsert_device(self.key, external_id, fields, external_url=url,
                                          overwrite=overwrite)
            except ValueError as exc:
                result.errors.append(f"{label}: {exc}")
                return False
            if action == "created":
                result.created += 1
            elif action == "updated":
                result.updated += 1
            else:
                result.skipped += 1
            return True

        if config.get("import_nodes", True):
            node_ips = self._node_ips(api)
            for res in (r for r in resources if r.get("type") == "node"):
                label = f"node {res.get('node') or res.get('id') or '?'}"
                try:
                    fields, ext_id = self._node_fields(api, res, node_ips)
                except (IntegrationError, ValueError, TypeError) as exc:
                    result.errors.append(f"{label}: {exc}")
                    continue
                if save(ext_id, fields, api.ui_url(f"node/{fields['hostname']}"), label):
                    counts["node"] += 1

        wanted = set()
        if config.get("import_vms", True):
            wanted.add("qemu")
        if config.get("import_containers", True):
            wanted.add("lxc")
        for res in (r for r in resources if r.get("type") in wanted):
            kind = res["type"]
            if config.get("skip_templates", True) and _truthy(res.get("template")):
                continue
            if config.get("only_running") and res.get("status") != "running":
                continue
            label = f"{kind} {res.get('vmid', '?')} ({res.get('name') or 'no name'})"
            try:
                vmid = int(res.get("vmid"))
                node = res.get("node")
                if not node:
                    raise ValueError("no node in the resource list")
                if kind == "qemu":
                    fields = self._vm_fields(api, node, vmid, res)
                else:
                    fields = self._ct_fields(api, node, vmid, res)
            except (IntegrationError, ValueError, TypeError) as exc:
                result.errors.append(f"{label}: {exc}")
                continue
            if save(f"{kind}:{vmid}", fields, api.ui_url(f"{kind}/{vmid}"), label):
                counts[kind] += 1

        result.message = (f"{counts['node']} nodes, {counts['qemu']} virtual machines, "
                          f"{counts['lxc']} containers")
        return result

    # --- nodes -----------------------------------------------------------------------------
    def _node_ips(self, api):
        """{node name: ip} from /cluster/status. Needs Sys.Audit on /; empty when refused."""
        try:
            status = api.get("/cluster/status") or []
        except IntegrationError:
            return {}
        return {s.get("name"): s.get("ip") for s in status
                if isinstance(s, dict) and s.get("type") == "node" and s.get("ip")}

    def _node_fields(self, api, res, node_ips):
        name = res.get("node")
        if not name:
            raise ValueError("no node name in the resource list")
        fields = {"hostname": name, "device_type": NODE_TYPE, "operating_system": "Proxmox VE"}
        ip = node_ips.get(name)
        online = res.get("status") == "online"
        if online:
            version = api.get(f"/nodes/{_seg(name)}/version") or {}
            fields["os_version"] = version.get("version") or version.get("release")
            if not ip:
                ip = self._node_network_ip(api, name)
        if ip:
            fields["ip_address"] = ip
        return fields, f"node:{name}"

    def _node_network_ip(self, api, name):
        """Fallback when cluster status has no IP: the address of the interface with the
        default gateway, else the first usable one."""
        try:
            ifaces = api.get(f"/nodes/{_seg(name)}/network") or []
        except IntegrationError:
            return None
        candidates = [i for i in ifaces if isinstance(i, dict) and usable_ipv4(i.get("address"))]
        for iface in candidates:
            if iface.get("gateway"):
                return iface["address"]
        return candidates[0]["address"] if candidates else None

    # --- virtual machines ------------------------------------------------------------------
    def _vm_fields(self, api, node, vmid, res):
        cfg = api.get(f"/nodes/{_seg(node)}/qemu/{vmid}/config") or {}
        fields = {
            "hostname": cfg.get("name") or res.get("name") or f"vm-{vmid}",
            "device_type": GUEST_TYPE,
            "mac_address": qemu_mac(cfg.get("net0")),
            "operating_system": QEMU_OSTYPES.get(cfg.get("ostype")),
        }
        if res.get("status") == "running" and agent_enabled(cfg.get("agent")):
            ip, osinfo = self._agent_info(api, node, vmid)
            if ip:
                fields["ip_address"] = ip
            if osinfo.get("name"):
                fields["operating_system"] = osinfo["name"]
                fields["os_version"] = osinfo.get("version-id") or osinfo.get("version")
        return fields

    def _agent_info(self, api, node, vmid):
        """Best effort: (ip, osinfo dict). Any failure (agent not running, token without the
        guest agent privilege, old agent) gives (None, {}) and is not an error."""
        base = f"/nodes/{_seg(node)}/qemu/{vmid}/agent"
        try:
            net = api.get(f"{base}/network-get-interfaces", timeout=AGENT_TIMEOUT) or {}
        except IntegrationError:
            return None, {}
        ip = first_ipv4(net.get("result") if isinstance(net, dict) else None)
        try:
            info = api.get(f"{base}/get-osinfo", timeout=AGENT_TIMEOUT) or {}
            info = info.get("result") if isinstance(info, dict) else None
        except IntegrationError:
            info = None
        return ip, (info if isinstance(info, dict) else {})

    # --- containers ------------------------------------------------------------------------
    def _ct_fields(self, api, node, vmid, res):
        cfg = api.get(f"/nodes/{_seg(node)}/lxc/{vmid}/config") or {}
        mac, static_ip = lxc_net(cfg.get("net0"))
        fields = {
            "hostname": cfg.get("hostname") or res.get("name") or f"ct-{vmid}",
            "device_type": GUEST_TYPE,
            "mac_address": mac,
            "operating_system": LXC_OSTYPES.get(cfg.get("ostype")),
        }
        ip = None
        if res.get("status") == "running":
            try:
                ip = first_ipv4(api.get(f"/nodes/{_seg(node)}/lxc/{vmid}/interfaces",
                                        timeout=AGENT_TIMEOUT))
            except IntegrationError:
                ip = None  # older Proxmox VE without this endpoint: use the static IP
        ip = ip or static_ip
        if ip:
            fields["ip_address"] = ip
        return fields


def _truthy(value):
    return str(value).strip().lower() in ("1", "true", "yes")


_NO_ACCESS = (
    "Connected, but the API token can see no nodes or guests. With privilege separation on "
    "(the default) the token needs its own permission: add the PVEAuditor role for the token "
    "on path / under Datacenter > Permissions."
)

INTEGRATION = ProxmoxIntegration()
