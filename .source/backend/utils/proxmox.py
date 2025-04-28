# backend/utils/proxmox.py

from proxmoxer import ProxmoxAPI
from proxmoxer.core import ResourceException
from backend.models.credentials import Credential

def human_readable_bytes(num, suffix='B'):
    """
    Convert a numeric byte value into a human-readable string (KiB, MiB, etc.).
    If `num` isn’t a plain int or float, show a placeholder instead of crashing.
    """
    if not isinstance(num, (int, float)):
        return '—'

    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return f"{num:.2f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.2f} Yi{suffix}"

def human_readable_time(seconds: int):
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts = []
    if days:    parts.append(f"{days}d")
    if hours:   parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    return " ".join(parts) if parts else "0m"

def get_proxmox_client(device):
    creds = device.credentials
    if not creds:
        raise ValueError("No credential found for this device")

    # pick credential with “proxmox” in the title, else first
    cred = next((c for c in creds if 'proxmox' in c.title.lower()), creds[0])
    password = cred.get_decrypted_password()
    username = cred.username
    if '@' not in username:
        username = f"{username}@pam"

    return ProxmoxAPI(
        host=device.ip_address,
        user=username,
        password=password,
        verify_ssl=False,
        port=8006
    )

def fetch_proxmox_details(device):
    client = get_proxmox_client(device)
    details = {}

    # ─── Host Summary ────────────────────────────────
    summary = {}
    nodes = client.nodes.get()
    for node in nodes:
        name = node['node']
        st = client.nodes(name).status.get()
        # Proxmox may return memory as a flat value ('mem') or as a dict ('memory')
        mem_val = st.get('mem')
        memory_info = st.get('memory')

        if isinstance(mem_val, (int, float)):
            raw_used = mem_val
            raw_total = st.get('maxmem') or st.get('totalmem')
        elif isinstance(memory_info, dict):
            raw_used = memory_info.get('used')
            raw_total = memory_info.get('total')
        else:
            raw_used = None
            raw_total = None

        summary[name] = {
            'cpu_pct': round(st.get('cpu', 0) * 100, 1),
            'mem_used': human_readable_bytes(raw_used) if isinstance(raw_used, (int, float)) else '—',
            'mem_total': human_readable_bytes(raw_total) if isinstance(raw_total, (int, float)) else '—',
            'uptime': human_readable_time(st.get('uptime', 0)),
        }
    details['summary'] = summary

    # ─── Virtual Machines ────────────────────────────
    vms = []
    for node in nodes:
        for vm in client.nodes(node['node']).qemu.get():
            vmid = vm['vmid']
            status = client.nodes(node['node']).qemu(vmid).status.current.get()
            vms.append({
                'node': node['node'],
                'name': vm.get('name'),
                'status': status.get('status'),
                'cpu_pct': round(status.get('cpu', 0) * 100, 1),
                'mem_used': human_readable_bytes(status.get('mem', 0)),
                'mem_total': human_readable_bytes(status.get('maxmem', 0)),
                'uptime': human_readable_time(status.get('uptime', 0)),
            })
    details['vms'] = vms

    # ─── LXC Containers ──────────────────────────────
    containers = []
    for node in nodes:
        for ct in client.nodes(node['node']).lxc.get():
            ctid = ct['vmid']
            status = client.nodes(node['node']).lxc(ctid).status.current.get()
            containers.append({
                'node': node['node'],
                'name': ct.get('name'),
                'status': status.get('status'),
                'cpu_pct': round(status.get('cpu', 0) * 100, 1),
                'mem_used': human_readable_bytes(status.get('mem', 0)),
                'mem_total': human_readable_bytes(status.get('maxmem', 0)),
                'uptime': human_readable_time(status.get('uptime', 0)),
            })
    details['containers'] = containers

    # ─── Storage Pools ───────────────────────────────
    pools = []
    for pool in client.storage.get():
        sid = pool['storage']
        # Base info from the listing
        entry = {
            'storage': sid,
            'type': pool.get('type'),
            # Proxmox returns 'avail' in the listing too
            'used': human_readable_bytes(pool.get('used', 0)),
            'avail': human_readable_bytes(pool.get('avail', 0)),
        }
        # Try the richer "status" endpoint if available
        try:
            stat = client.storage(sid).status.get()
            entry['used']       = human_readable_bytes(stat.get('used', pool.get('used', 0)))
            entry['available']  = human_readable_bytes(stat.get('avail', pool.get('avail', 0)))
        except ResourceException as e:
            # 501 Not Implemented will land here
            entry['available']  = entry.pop('avail', 'n/a')
            entry['note']       = "Detailed status not supported for this pool"
        except Exception:
            entry['available']  = entry.pop('avail', 'n/a')
            entry['note']       = "Error fetching detailed status"

        pools.append(entry)
    details['storage'] = pools

    return details
