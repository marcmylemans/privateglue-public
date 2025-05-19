from flask import Blueprint, render_template, flash, url_for, redirect
from flask_login import login_required
from backend.models.devices import Device
from backend.utils.snmp import snmp_get, get_interface_table, get_vlans, get_port_pvid, get_vlan_membership

network_bp = Blueprint("network", __name__, url_prefix="/network")

@network_bp.route("/scan/<int:device_id>")
@login_required
def scan_device(device_id):
    device = Device.query.get_or_404(device_id)
    if device.device_type.lower() != "switch":
        flash("SNMP scan only available for switches.", "warning")
        return redirect(url_for("devices.view", device_id=device.id))

    # <-- define host from the device record
    host = device.ip_address

    data = {
        "sys_descr":  snmp_get(host,   "1.3.6.1.2.1.1.1.0"),
        "sys_uptime": snmp_get(host,   "1.3.6.1.2.1.1.3.0"),
        "interfaces": get_interface_table(host),
        "vlans":      get_vlans(host),
        "port_pvid":  get_port_pvid(host),
        "vlan_members": get_vlan_membership(host),
    }
    return render_template("network/scan.html", device=device, data=data)
