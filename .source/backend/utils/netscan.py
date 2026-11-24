"""Scan a network from the server itself and put the result in the discovered list.

This is the built-in counterpart of the standalone probe (the scanning code is a copy of
its logic, kept small on purpose so the app does not depend on the probe repository).

It is OFF until an administrator turns it on under Devices > Discovered. Whoever runs the
server has the last word through ALLOW_SERVER_SCAN: "true" keeps it on, "never" keeps it off
and takes the switch away. That last one is for a shared or hosted server, where a scan
would let people look around the hosting network.
"""
import ipaddress
import json
import os
import platform
import re
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from backend.utils import probe_store

STATE_FILE = "scan_state.json"
SETTING_FILE = "server_scan.json"
MAX_HOSTS = 1024               # a /22
WORKERS = 64
STALE_AFTER = 15 * 60          # a scan "running" for longer than this is treated as dead
TCP_PORTS = (443, 80, 22, 445, 3389)  # tried when a device does not answer ping (Windows often doesn't)
PRIVATE_BLOCKS = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
MAC_RE = re.compile(r"(?<![0-9A-Fa-f])((?:[0-9A-Fa-f]{1,2}[:-]){5}[0-9A-Fa-f]{1,2})(?![0-9A-Fa-f])")
IPV4_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")


class ScanError(Exception):
    """A problem the admin can fix; the message is shown on the page."""


def policy():
    """What the server's own settings say about scanning:
    "on"     ALLOW_SERVER_SCAN=true: always on, the switch in the app is fixed.
    "never"  ALLOW_SERVER_SCAN=never: always off, administrators cannot turn it on.
    "switch" anything else, including the default "false": the switch in the app decides."""
    value = os.environ.get("ALLOW_SERVER_SCAN", "").strip().lower()
    if value in ("1", "true", "yes", "on"):
        return "on"
    if value in ("never", "disabled", "locked"):
        return "never"
    return "switch"


def _switch_is_on():
    try:
        with open(probe_store._path(SETTING_FILE), encoding="utf-8") as handle:
            return json.load(handle).get("enabled") is True
    except (OSError, ValueError, AttributeError):
        return False  # no file, or one that cannot be read: off


def is_enabled():
    decided = policy()
    if decided == "switch":
        return _switch_is_on()
    return decided == "on"


def set_enabled(enabled, by=""):
    """Turn the switch in the app on or off. The file is shared by all workers."""
    decided = policy()
    if decided == "never":
        raise ScanError("Scanning from this server is disabled in the server's settings.")
    if decided == "on":
        raise ScanError("Scanning is turned on in the server's settings (ALLOW_SERVER_SCAN), so it cannot be changed here.")
    record = {"enabled": bool(enabled), "changed_by": str(by)[:80], "changed_at": int(time.time())}
    probe_store._write_atomic(probe_store._path(SETTING_FILE), json.dumps(record).encode("utf-8"))
    return bool(enabled)


# --- input ------------------------------------------------------------------

def parse_network(text):
    """Validate what the admin typed. Only home and office ranges, and not too large."""
    text = (text or "").strip()
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){2}", text):
        text += ".0/24"
    if "/" not in text:
        raise ScanError("Give the network with its size, for example 192.168.1.0/24.")
    try:
        network = ipaddress.ip_network(text, strict=False)
    except ValueError:
        raise ScanError(f"'{text}' is not a network. Use a form like 192.168.1.0/24.")
    if network.version != 4:
        raise ScanError("Only IPv4 networks can be scanned.")
    if not any(network.subnet_of(block) for block in PRIVATE_BLOCKS):
        raise ScanError("Only private networks can be scanned: 10.x.x.x, 172.16 to 172.31.x.x or 192.168.x.x.")
    hosts = max(network.num_addresses - 2, 1)
    if hosts > MAX_HOSTS:
        raise ScanError(f"{network} has {hosts} addresses. The limit is {MAX_HOSTS} per scan: scan it in smaller parts.")
    return network


def server_address():
    """The address this server uses to reach other machines, or "" when unknown.
    Nothing is sent: connecting a UDP socket only asks the system which address it would use."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 9))
        return sock.getsockname()[0]
    except OSError:
        return ""
    finally:
        sock.close()


def suggested_network():
    """The /24 around the server's own address when that is a private address, else ""."""
    try:
        ip = ipaddress.ip_address(server_address())
    except ValueError:
        return ""
    if not any(ip in block for block in PRIVATE_BLOCKS):
        return ""
    return str(ipaddress.ip_network(f"{ip}/24", strict=False))


# --- finding devices --------------------------------------------------------

def ping_host(ip):
    command = ["ping", "-n", "1", "-w", "1000", ip] if platform.system() == "Windows" else ["ping", "-c", "1", "-W", "1", ip]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0 and b"unreachable" not in result.stdout.lower()


def tcp_answers(ip, ports=TCP_PORTS, timeout=0.5):
    """True when the address accepts a connection on one of a few common ports.

    A refused connection is NOT counted: firewalls between networks often refuse on behalf
    of addresses that do not exist, which would fill the list with phantom devices."""
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((ip, port))
            return True
        except OSError:
            continue
        finally:
            sock.close()
    return False


def host_alive(ip):
    return ping_host(ip) or tcp_answers(ip)


def normalize_mac(text):
    parts = re.split(r"[:-]", text.strip())
    if len(parts) != 6:
        return ""
    try:
        mac = ":".join(f"{int(part, 16):02x}" for part in parts)
    except ValueError:
        return ""
    return "" if mac in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff") else mac


def parse_neighbors(text):
    table = {}
    for line in text.splitlines():
        ip_match, mac_match = IPV4_RE.search(line), MAC_RE.search(line)
        if ip_match and mac_match:
            mac = normalize_mac(mac_match.group(1))
            if mac:
                table[ip_match.group(1)] = mac
    return table


def read_neighbors():
    """IP to MAC from the system's neighbour table. Inside a container on Docker's default
    network this only knows the Docker gateway, so MAC addresses need host networking."""
    for command in (["ip", "neigh"], ["arp", "-an"]):
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15)
        except (subprocess.TimeoutExpired, OSError):
            continue
        table = parse_neighbors(result.stdout.decode(errors="replace"))
        if table:
            return table
    return {}


# --- names ------------------------------------------------------------------
# Three places a device's name can come from, asked in this order:
#   1. DNS: the reverse (PTR) record, when your DNS server has one.
#   2. NetBIOS: Windows machines, NAS boxes and anything running Samba tell their name
#      when asked on UDP port 137.
#   3. mDNS: Apple devices, most Linux machines, printers and smart-home gear tell their
#      ".local" name when asked on UDP port 5353.
# 2 and 3 are one small question sent straight to the device, only to addresses that
# already answered the scan. A device that does not speak them simply stays silent.

NAME_TIMEOUT = 1.0
NAME_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,251}[A-Za-z0-9])?")


def clean_name(name):
    """A name as a device reported it, or "" when it is not a plausible host name. Names come
    from machines on the network, so nothing odd is passed on."""
    name = (name or "").strip().rstrip(".")
    return name if NAME_RE.fullmatch(name) else ""


def reverse_dns(ip):
    try:
        name = clean_name(socket.gethostbyaddr(ip)[0])
    except (OSError, UnicodeError):
        return ""
    return "" if name == ip else name


def _ask(ip, port, packet, timeout):
    """Send one UDP question to one device and return its answer, or b"" for none."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(packet, (ip, port))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data, sender = sock.recvfrom(2048)
            if sender[0] == ip and data[:2] == packet[:2]:  # from that device, to this question
                return data
    except OSError:
        pass
    finally:
        sock.close()
    return b""


def _skip_name(data, offset):
    """Position just after the DNS-style name that starts at offset."""
    while True:
        length = data[offset]
        if length == 0:
            return offset + 1
        if length & 0xC0 == 0xC0:  # a pointer to an earlier name: two bytes
            return offset + 2
        offset += 1 + length


def parse_netbios_names(data):
    """The machine name from a NetBIOS "node status" answer, or ""."""
    try:
        if len(data) < 12 or not data[2] & 0x80 or int.from_bytes(data[6:8], "big") < 1:
            return ""
        offset = _skip_name(data, 12)
        offset += 10  # type, class, time to live, data length
        count = data[offset]
        offset += 1
        for _ in range(count):
            entry = data[offset:offset + 18]
            offset += 18
            if len(entry) < 18:
                break
            suffix, flags = entry[15], int.from_bytes(entry[16:18], "big")
            # Suffix 0x00 without the group flag is the computer's own name; the same
            # suffix with the flag is its workgroup or domain.
            if suffix == 0x00 and not flags & 0x8000:
                return clean_name(entry[:15].decode("ascii", errors="ignore"))
    except IndexError:
        pass
    return ""


def netbios_name(ip, port=137, timeout=NAME_TIMEOUT):
    query_id = os.urandom(2)
    # One question: "node status" for the wildcard name "*".
    packet = query_id + b"\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00" + b"\x20CK" + b"A" * 30 + b"\x00\x00\x21\x00\x01"
    return parse_netbios_names(_ask(ip, port, packet, timeout))


def _read_name(data, offset, depth=0):
    labels = []
    while depth < 8:
        length = data[offset]
        if length == 0:
            break
        if length & 0xC0 == 0xC0:
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            labels.append(_read_name(data, pointer, depth + 1))
            break
        labels.append(data[offset + 1:offset + 1 + length].decode("utf-8", errors="ignore"))
        offset += 1 + length
    return ".".join(label for label in labels if label)


def parse_mdns_pointer(data):
    """The host name from an answer to a reverse (PTR) question, or ""."""
    try:
        if len(data) < 12 or not data[2] & 0x80:
            return ""
        questions, answers = int.from_bytes(data[4:6], "big"), int.from_bytes(data[6:8], "big")
        offset = 12
        for _ in range(questions):
            offset = _skip_name(data, offset) + 4
        for _ in range(answers):
            offset = _skip_name(data, offset)
            record_type = int.from_bytes(data[offset:offset + 2], "big")
            length = int.from_bytes(data[offset + 8:offset + 10], "big")
            offset += 10
            if record_type == 12:  # PTR
                return clean_name(_read_name(data, offset))
            offset += length
    except IndexError:
        pass
    return ""


def mdns_name(ip, port=5353, timeout=NAME_TIMEOUT):
    query_id = os.urandom(2)
    question = b"".join(bytes([len(part)]) + part.encode() for part in reversed(ip.split("."))) + b"\x07in-addr\x04arpa\x00"
    # Type PTR; class IN with the "answer me directly" bit, so the reply comes to us and
    # not to the multicast group.
    packet = query_id + b"\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00" + question + b"\x00\x0c\x80\x01"
    return parse_mdns_pointer(_ask(ip, port, packet, timeout))


def lookup_hostname(ip, sources=None):
    for source in sources or (reverse_dns, netbios_name, mdns_name):
        name = source(ip)
        if name:
            return name
    return ""


def own_mac(ip):
    """The MAC address of this server's own network card with that address, or "". The
    neighbour table lists other machines only, so the server would show up without one."""
    try:
        result = subprocess.run(["ip", "-o", "-4", "addr", "show"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
        for line in result.stdout.decode(errors="replace").splitlines():
            fields = line.split()
            if len(fields) >= 4 and fields[2] == "inet" and fields[3].split("/")[0] == ip:
                name = fields[1].split("@")[0]
                with open(f"/sys/class/net/{name}/address", encoding="ascii") as handle:
                    return normalize_mac(handle.read())
    except (subprocess.TimeoutExpired, OSError, ValueError):
        pass
    return ""


def scan_network(network, alive=None, hostname=lookup_hostname, neighbors=read_neighbors, use_tcp=True,
                 own_address=server_address, own_mac_lookup=own_mac):
    alive = alive or (host_alive if use_tcp else ping_host)
    addresses = [str(ip) for ip in network.hosts()]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        up = [ip for ip, ok in zip(addresses, pool.map(alive, addresses)) if ok]
        names = dict(zip(up, pool.map(hostname, up)))
    macs = neighbors() if up else {}
    me = own_address() if up else ""
    if me in up and not macs.get(me):
        macs[me] = own_mac_lookup(me)
    return [{"ip_address": ip, "hostname": names.get(ip, ""), "mac_address": macs.get(ip, "")} for ip in up]


# --- state shared by all workers --------------------------------------------

def _state_path():
    return os.path.join(probe_store.DATA_DIR, STATE_FILE)


def read_state():
    """{"status": "idle" | "running" | "done" | "error", "network", "started_at", "found", "message"}"""
    try:
        with open(_state_path(), "rb") as handle:
            state = json.loads(handle.read().decode())
    except (OSError, ValueError):
        return {"status": "idle"}
    if state.get("status") == "running" and time.time() - state.get("started_at", 0) > STALE_AFTER:
        state.update(status="error", message="The scan was interrupted (the server restarted). Start it again.")
    return state


def _write_state(**state):
    probe_store._write_atomic(_state_path(), json.dumps(state).encode())


def run_scan(network, scan=None, use_tcp=True):
    """Scan now, in this thread, and store the result. Never raises."""
    started = int(time.time())
    try:
        devices = scan(network) if scan else scan_network(network, use_tcp=use_tcp)
        probe_store.save_discovered(devices)
        _write_state(status="done", network=str(network), started_at=started, finished_at=int(time.time()),
                     found=len(devices), message="")
    except Exception as exc:  # keep the state readable whatever went wrong
        _write_state(status="error", network=str(network), started_at=started, found=0,
                     message=f"The scan failed: {type(exc).__name__}")


def start_scan(network_text, use_tcp=True):
    """Validate, mark the scan as running and start it in the background.
    Raises ScanError when scanning is off, the input is wrong or a scan is already running."""
    if not is_enabled():
        raise ScanError("Scanning from the server is turned off.")
    network = parse_network(network_text)
    if read_state().get("status") == "running":
        raise ScanError("A scan is already running. Wait until it has finished.")
    _write_state(status="running", network=str(network), started_at=int(time.time()), found=0, message="")
    thread = threading.Thread(target=run_scan, args=(network,), kwargs={"use_tcp": use_tcp},
                              name="server-scan", daemon=True)
    thread.start()
    return network, thread
