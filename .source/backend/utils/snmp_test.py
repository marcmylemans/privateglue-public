import sys
from snmp import snmp_get, get_interface_table, get_vlans

if __name__ == "__main__":
    host = "10.48.10.202"
    print(f"Testing SNMP on {host}\n")

    # Test system description
    sys_descr = snmp_get(host, "1.3.6.1.2.1.1.1.0")
    print(f"System Description: {sys_descr}")

    # Test interface table
    print("\nInterface Table:")
    try:
        interfaces = get_interface_table(host)
        for iface in interfaces:
            print(iface)
    except Exception as e:
        print(f"Error fetching interfaces: {e}")

    # Test VLANs
    print("\nVLANs:")
    try:
        vlans = get_vlans(host)
        for vlan in vlans:
            print(vlan)
    except Exception as e:
        print(f"Error fetching VLANs: {e}")
