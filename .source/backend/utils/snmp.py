import os
import asyncio

from puresnmp import V2C, V1
from puresnmp.api.raw import Client
from puresnmp.api.pythonic import PyWrapper

COMMUNITY = os.getenv("SNMP_COMMUNITY", "public")
PORT      = int(os.getenv("SNMP_PORT", 161))

def _make_wrapper(host: str, cred):
    client  = Client(host, cred, port=PORT)
    return PyWrapper(client)

def snmp_get(host: str, oid: str):
    for cred_cls in (V2C, V1):
        wrapper = _make_wrapper(host, cred_cls(COMMUNITY))
        try:
            return asyncio.run(wrapper.get(oid))
        except Exception:
            continue
    return None

def snmp_walk(host: str, oid: str):
    import types
    async def walk_all(wrapper, oid):
        results = []
        async for vb in wrapper.walk(oid):
            results.append(vb)
        return results

    for cred_cls in (V2C, V1):
        wrapper = _make_wrapper(host, cred_cls(COMMUNITY))
        try:
            print(f"[DEBUG] Walking OID {oid} with {cred_cls.__name__}")
            results = asyncio.run(walk_all(wrapper, oid))
            found = False
            for vb in results:
                # Use vb.value instead of vb.pyvalue
                print(f"[DEBUG] OID: {vb.oid}, Value: {vb.value}")
                found = True
                yield vb.oid, vb.value
            if found:
                return
        except Exception as e:
            print(f"[DEBUG] Exception in snmp_walk: {e}")
            continue
    return

def get_interface_table(host: str):
    """
    Fetch interface names (ifDescr) and statuses (ifOperStatus), then return:
      [ { 'index': '1', 'name': 'Gig1/0/1', 'status': 1 }, … ]
    Excludes VLAN, loopback, CPU, Link Aggregate, DEFAULT_VLAN, and other non-physical interfaces by name or index.
    Dynamically includes only interfaces that look like real physical ports based on their name (e.g. containing 'port', 'gigabit', 'eth', or 'ge'),
    or if the name is just a number (to support Aruba and similar switches).
    """
    # Walk ifDescr
    names = {}
    for oid, val in snmp_walk(host, ".1.3.6.1.2.1.2.2.1.2"):
        idx = oid.rsplit(".", 1)[-1]
        name = val.decode(errors="ignore") if isinstance(val, (bytes, bytearray)) else str(val)
        names[idx] = name

    # Walk ifOperStatus
    statuses = {}
    for oid, val in snmp_walk(host, "1.3.6.1.2.1.2.2.1.8"):
        idx = oid.rsplit(".", 1)[-1]
        statuses[idx] = val if isinstance(val, int) else int.from_bytes(val, "big")

    # Build a sorted list, filtering out non-physical interfaces
    table = []
    for idx in sorted(names.keys(), key=int):
        name = names[idx]
        lname = name.lower()
        # Heuristic: include if name looks like a real port OR is just a number (Aruba)
        is_physical = (
            name.isdigit() or
            ("port" in lname or "gigabit" in lname or "eth" in lname or "ge" in lname)
        ) and not (
            lname.startswith("vlan") or
            "loopback" in lname or
            "cpu" in lname or
            "aggregate" in lname or
            lname == "default_vlan" or
            (name.isupper() and not name.startswith("Port"))
        )
        if not is_physical:
            continue
        table.append({
            "index":  idx,
            "name":   names[idx],
            "status": statuses.get(idx)
        })
    return table


def get_vlans(host: str):
    """
    Returns list of VLAN dicts: [{ 'vlan_id': int, 'name': str }, … ]
    via dot1qVlanStaticName (.1.3.6.1.2.1.17.7.1.4.3.1.1)
    """
    vlans = {}
    for oid, val in snmp_walk(host, ".1.3.6.1.2.1.17.7.1.4.3.1.1"):
        vid = int(oid.rsplit(".",1)[-1])
        name = val.decode(errors="ignore") if isinstance(val,(bytes,bytearray)) else str(val)
        vlans[vid] = name

    return [{"vlan_id": vid, "name": vlans[vid]} for vid in sorted(vlans)]

def get_port_pvid(host: str):
    """
    Returns { port_index: pvid } via dot1qPvid (1.3.6.1.2.1.17.7.1.4.5.1.1)
    """
    pvids = {}
    for oid, val in snmp_walk(host, "1.3.6.1.2.1.17.7.1.4.5.1.1"):
        idx = int(oid.rsplit(".",1)[-1])
        pvids[idx] = int(val) if isinstance(val,int) else int.from_bytes(val, "big")
    return pvids

def get_vlan_membership(host: str):
    """
    Returns { vlan_id: [port_index,…] } via dot1qVlanStaticEgressPorts
    (1.3.6.1.2.1.17.7.1.4.2.1.4) which is a bitstring per VLAN.
    """
    memb = {}
    for oid, val in snmp_walk(host, "1.3.6.1.2.1.17.7.1.4.2.1.4"):
        vid = int(oid.rsplit(".",1)[-1])
        # val is bytes: each bit represents a port (1-based)
        bits = "".join(f"{b:08b}" for b in val)
        ports = [i+1 for i, bit in enumerate(bits) if bit == "1"]
        memb[vid] = ports
    return memb

def get_vlan_port_types(host):
    """
    Returns { vlan_id: { 'tagged': [port_index], 'untagged': [port_index] } }
    Untagged = port's PVID matches VLAN ID; Tagged = port is member but PVID != VLAN ID
    Only includes ports that are real physical interfaces (as determined by get_interface_table).
    """
    # Get set of real physical port indices
    physical_ports = set(iface['index'] for iface in get_interface_table(host))
    vlan_members = get_vlan_membership(host)  # {vlan_id: [port_index, ...]}
    pvids = get_port_pvid(host)               # {port_index: pvid}
    result = {}
    for vlan_id, ports in vlan_members.items():
        tagged = []
        untagged = []
        for port in ports:
            if str(port) not in physical_ports:
                continue  # skip non-physical ports
            if pvids.get(port) == vlan_id:
                untagged.append(port)
            else:
                tagged.append(port)
        result[vlan_id] = {
            "tagged": tagged,
            "untagged": untagged,
        }
    return result