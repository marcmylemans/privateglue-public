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
    for cred_cls in (V2C, V1):
        wrapper = _make_wrapper(host, cred_cls(COMMUNITY))
        try:
            for vb in asyncio.run(wrapper.walk(oid)):
                yield vb.oid, vb.pyvalue
            return
        except Exception:
            continue
    return

def get_interface_table(host: str):
    """
    Fetch interface names (ifDescr) and statuses (ifOperStatus), then return:
      [ { 'index': '1', 'name': 'Gig1/0/1', 'status': 1 }, … ]
    """
    # Walk ifDescr
    names = {}
    for oid, val in snmp_walk(host, ".1.3.6.1.2.1.2.2.1.2"):
        idx = oid.rsplit(".", 1)[-1]
        names[idx] = val.decode(errors="ignore") if isinstance(val, (bytes, bytearray)) else str(val)

    # Walk ifOperStatus
    statuses = {}
    for oid, val in snmp_walk(host, "1.3.6.1.2.1.2.2.1.8"):
        idx = oid.rsplit(".", 1)[-1]
        # val may be int or bytes
        statuses[idx] = val if isinstance(val, int) else int.from_bytes(val, "big")

    # Build a sorted list
    table = []
    for idx in sorted(names.keys(), key=int):
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