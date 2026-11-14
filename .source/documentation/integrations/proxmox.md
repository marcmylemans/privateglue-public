# Proxmox VE

Imports a Proxmox VE cluster (or a single host) into the PrivateGlue device list: the nodes
themselves, the QEMU virtual machines and the LXC containers. It only reads from Proxmox VE and
never changes anything there. It never deletes devices in PrivateGlue.

This is separate from the "Fetch info" button on a Proxmox device page. That button uses a
credential stored on the device. This integration has its own settings and uses an API token.

## What you need

- PrivateGlue must reach port 8006 of one Proxmox VE node. In a cluster any node will do: the
  API answers for the whole cluster.
- An API token with read-only rights (below). Password login is not supported.

## Create the API token (least privilege)

1. In the Proxmox VE web UI go to **Datacenter > Permissions > Users** and add a user for this,
   for example `privateglue` in realm `pve` (Proxmox VE authentication server). It does not
   need a password you will ever use.
2. Go to **Datacenter > Permissions > API Tokens**, click **Add**, pick that user and give the
   token an ID such as `import`. Leave **Privilege Separation** ticked (the default).
3. Copy the **Token ID** (`privateglue@pve!import`) and the **Secret**. The secret is shown only
   once.
4. Go to **Datacenter > Permissions**, click **Add > API Token Permission**, path `/`, the token
   you just made, role **PVEAuditor**, propagate ticked.

**Privilege separation.** With it on (the default and the safer choice) the token has only the
permissions you give the token itself, and never more than its user has. So with privilege
separation on, give the role to the token (step 4), not only to the user. If you turn privilege
separation off, the token simply has all the rights of its user. A token with no permissions at
all does not get an error from Proxmox, it just sees nothing; PrivateGlue then tells you to add
the PVEAuditor role.

PVEAuditor is read only. It covers what this integration needs: the resource list, node status
and version, cluster status (node IP addresses) and the configuration of every VM and container
(`VM.Audit`).

**Guest agent (optional, for VM IP addresses and exact OS names).** PVEAuditor does not include
the guest agent privilege. Without it the import still works, VMs just get no IP address and the
OS name comes from the VM's "Guest OS" setting. If you want it, add a custom role with this one
privilege and give it to the token on `/vms` (or `/`):

- Proxmox VE 9: `VM.GuestAgent.Audit` ("issue informational QEMU guest agent commands").
- Proxmox VE 8: `VM.Monitor`. This privilege was removed in Proxmox VE 9 and replaced by the
  `VM.GuestAgent.*` privileges. After an upgrade to 9, a custom role with `VM.Monitor` must be
  changed to `VM.GuestAgent.Audit`.

Container IP addresses do not need anything extra: they are covered by `VM.Audit`.

## Settings

| Setting | What it does |
| --- | --- |
| Host | Host name or IP address of any node, for example `pve1.lan` or `192.168.1.10`. Only the name or address: no `https://`, no port, no path. |
| Port | The API port. Default 8006. |
| API token ID | `user@realm!tokenname`, for example `privateglue@pve!import`. |
| API token secret | The secret shown when you created the token. Stored encrypted, never shown again. Leave empty when saving to keep the saved one. |
| Verify the TLS certificate | On by default. A default Proxmox VE install uses a self-signed certificate, so the connection fails until you either install a trusted certificate (for example through ACME under the node's **System > Certificates**) or turn this off. Turning it off is common in a homelab, but then anyone in the network path could pose as your Proxmox VE host. |
| Import nodes | Import the cluster nodes as servers. On by default. |
| Import virtual machines | Import QEMU virtual machines. On by default. |
| Import containers | Import LXC containers. On by default. |
| Skip templates | Leave VM and container templates out. On by default. |
| Only running guests | Leave VMs and containers out that are not running. Off by default. Nodes are always imported when "Import nodes" is on. |
| Location for imported devices | Optional text put in the location field of every imported device, for example `Homelab rack`. |
| Overwrite PrivateGlue values | Off by default: only empty fields are filled in, so what you typed by hand stays. On: Proxmox VE values replace the PrivateGlue values on every sync. |

**Test connection** checks the address, the certificate and the token and answers with the
version and the number of nodes, for example "Connected to Proxmox VE 8.2.4, 3 nodes".

## What is imported

| PrivateGlue field | Node | Virtual machine | Container |
| --- | --- | --- | --- |
| Hostname | Node name | VM name (`vm-<id>` when it has none) | Container host name (`ct-<id>` when it has none) |
| Type | Server | VM | VM |
| Operating system | Proxmox VE | From the guest agent when it runs, else from the "Guest OS" setting (for example `l26` becomes Linux, `win11` becomes Windows 11) | From the container's OS type (Debian, Ubuntu, Alpine Linux, ...) |
| Version | Proxmox VE version of the node | From the guest agent, when it runs | Not set |
| IP address | From cluster status, else from the node's network config (the interface with the default gateway) | First IPv4 address reported by the guest agent, skipping loopback and link-local (169.254.x.x) | Live address of the running container, else the static `ip=` of `net0` (nothing for DHCP) |
| MAC address | Not set | From `net0` | From `net0` |
| Location | The location setting, when filled in | same | same |

Each imported device gets a link back to it in the Proxmox VE web UI.

Containers get the type **VM** as well. PrivateGlue has no separate container type, and a new
type value would show up with a generic icon and next to the normal types in the type filter.
You can still tell them apart: the link on the device page says `lxc:<id>` and the operating
system is the container's distribution.

### How devices are matched

A guest is recognised by its VM ID (`qemu:<id>` or `lxc:<id>`), not by its node, so a VM that
migrates to another node stays the same device. A node is recognised by its name (`node:<name>`).
On the first sync a device you already entered by hand is adopted when the MAC address or the
host name matches, so you do not get duplicates.

Notes:

- Only the guest agent and `net0` are used. A VM with several network cards gets the MAC of
  `net0` only.
- The guest agent is only asked when the VM is running and the agent option is enabled in the VM's
  options. A VM whose agent does not answer, or a token without the guest agent privilege, is not
  an error: the VM is imported without an IP address.
- `win11` in Proxmox VE also covers Windows Server 2022 and 2025, and `win10` covers Server
  2016 and 2019. Without the guest agent such a VM is shown as "Windows 11" or "Windows 10".
  With the agent running you get the exact name.
- Offline nodes are imported with their name and the IP from cluster status, without a version.

## What is not imported

Storage, disks, CPU and memory sizes, tags, pools, HA state, backups, snapshots, notes and
anything else not in the table above. Devices removed from Proxmox VE stay in PrivateGlue; delete
them by hand when you want to.

## Cost and limits

Proxmox VE has no paging: one call lists every node and guest in the cluster. After that, a sync
makes per item:

- per online node: 1 call (version), plus 1 when cluster status has no IP for it;
- per VM: 1 call (configuration), plus up to 2 guest agent calls when it runs with the agent on;
- per container: 1 call (configuration), plus 1 when it runs (live IP).

So a cluster with 3 nodes and 100 running guests takes about 300 calls. That is fine for a sync
every hour or every day. With very large clusters, use "Only running guests" or turn off what you
do not need. Each call times out after 20 seconds (8 seconds for guest agent and container
interface calls). One guest that fails is listed in the run history and the rest of the sync
continues.
