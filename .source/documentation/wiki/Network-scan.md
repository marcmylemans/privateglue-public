# Network scan

PrivateGlue can find the devices on your network for you. Whatever a scan finds goes into a review list under **Devices > Discovered**. Nothing is added to your inventory until you pick what to import. Devices that share a hostname, IP or MAC address with one you already have are marked and left unticked.

There are two ways to scan. They fill the same list, and each scan replaces the previous list.

| | Scan from this server | The probe |
|---|---|---|
| What it is | A button in PrivateGlue | A small separate program |
| Reaches | Networks the PrivateGlue server can reach | Any network you run it in |
| Set-up | One click | Download, address and key |
| Use it when | PrivateGlue runs inside the network you want to scan | The network is elsewhere: another VLAN, another site, a customer |

## Scan from this server

### Turn it on

Sign in as an administrator, open **Devices > Discovered** and click **Turn on scanning from this server**. It works straight away, without a restart. **Turn off** in the same place switches it off again.

It is off by default, because on a server you share with others it would let administrators look around that server's network.

Whoever runs the server can overrule the switch with the `ALLOW_SERVER_SCAN` setting (see [Configuration](Configuration)):

| Value | Effect |
|---|---|
| `false` (default) | The switch in the app decides. |
| `true` | Always on. The switch cannot turn it off. |
| `never` | Always off. Administrators cannot turn it on. Use this on a shared or hosted server. |

### Scan

1. Sign in as an administrator and open **Devices > Discovered**.
2. Under **Scan from this server**, enter the network, for example `192.168.1.0/24`.
3. Click **Scan now**. The page refreshes by itself. A scan of 254 addresses usually takes under a minute.

Limits: private networks only (`10.x.x.x`, `172.16` to `172.31.x.x`, `192.168.x.x`), at most 1024 addresses per scan, one scan at a time.

**Also find devices that do not answer ping** is ticked by default. Windows machines often ignore ping, so PrivateGlue also tries a few common ports (web, SSH, file sharing, remote desktop). Untick it if the list fills up with devices that do not exist, which can happen behind some firewalls.

### Where the names come from

For every device that answers, the server tries three sources and takes the first that gives a name:

| Source | Finds | Needs |
|---|---|---|
| DNS | The name your DNS server has for the address | A reverse (PTR) record. Many routers and DHCP servers create these by themselves; otherwise add them on your DNS server. |
| NetBIOS | Windows computers, NAS boxes, anything running Samba | The device answers on UDP port 137. Windows does when file sharing is allowed through its firewall. |
| mDNS | Apple devices, most Linux machines, printers, smart-home gear (`name.local`) | The device answers on UDP port 5353. Usually only for a server in the same network segment. |

A device that offers none of these shows with its IP address as its name. That is common for plain Linux servers and containers without a DNS record. You can rename a device after importing it.

If most of your devices show as an address: check that the server uses your own DNS server (not a public one), and that this DNS server has reverse records for the network.

### MAC addresses need the host network

With the normal compose file, the container sits on Docker's own network. It can reach your network and finds devices and their names, but it cannot see MAC addresses. To get those, run PrivateGlue on the host network with the second compose file:

```bash
docker compose down        # stop the normal one. Do NOT add -v
curl -fsSL https://raw.githubusercontent.com/marcmylemans/privateglue-public/main/docker-compose.host.yml -o docker-compose.host.yml
docker compose -f docker-compose.host.yml up -d
```

Do this in the same folder as before. Your data and the encryption key stay in place.

Things to know about the host network:

- It works on Linux hosts. Docker Desktop on Windows and macOS does not provide a real host network.
- PrivateGlue then listens directly on the host, on `PRIVATEGLUE_PORT` (default 5000), on every address the host has. Protect the port with the host's firewall or put a reverse proxy in front.
- Scanning is on by default in this file.
- From now on, use `-f docker-compose.host.yml` in every compose command, for example `docker compose -f docker-compose.host.yml pull`.

MAC addresses are only known for devices on the same network segment as the server. Devices behind a router show without one.

## The probe

The probe is a small program for Windows, Linux and macOS. Run it on any machine inside the network you want to scan. It sends what it finds to PrivateGlue.

### Set it up

1. In PrivateGlue, open **Devices > Discovered**. The section **Scan another network with the probe** shows the download link, this server's address and, for administrators, the API key.
2. Download the probe from its [releases page](https://github.com/marcmylemans/PrivateGlue-Probe/releases/latest). Windows users take `probe.exe`. On Linux and macOS, run `probe.py` with Python.
3. Give the probe the address and the key, then run it.

Windows (PowerShell):

```powershell
$env:PRIVATEGLUE_URL = "https://glue.example.com"
$env:PRIVATEGLUE_API_KEY = "paste-the-key-here"
.\probe.exe
```

Linux and macOS:

```bash
export PRIVATEGLUE_URL="https://glue.example.com"
export PRIVATEGLUE_API_KEY="paste-the-key-here"
python3 probe.py
```

To see what it would find without sending anything, add `--dry-run`.

4. Back in PrivateGlue, review the list under **Devices > Discovered** and import what you want.

### About the key

- The key only allows sending a list of discovered devices. It cannot read anything from PrivateGlue.
- Only administrators see it.
- If it may have leaked, click **Create a new key**. The old key stops working at once. Give the new one to your probes.
- Use an `https://` address whenever the probe is not on the same private network as PrivateGlue.

### Run it on a schedule

The probe runs once and exits. Use Task Scheduler on Windows or cron on Linux to run it regularly. The full list of options is in the [probe's own guide](https://github.com/marcmylemans/PrivateGlue-Probe#readme).

## Only scan networks you are allowed to scan

A scan sends a ping, and with the port check a few connection attempts, to every address in the range. Do this on your own networks, or with the owner's permission.
