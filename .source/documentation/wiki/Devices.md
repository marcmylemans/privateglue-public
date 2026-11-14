# Devices

The device list is your inventory: servers, virtual machines, network gear, laptops and anything else you want to document.

## Ways to add devices

| Way | Good for | Where |
|---|---|---|
| By hand | One device | **Devices > Add device** |
| CSV file | A list from a spreadsheet or another tool | **Devices > Import > From a CSV file** |
| Network scan | Finding what is on your network | **Devices > Import > Scan your network**. See [Network scan](Network-scan). |
| Integration | Keeping in step with NetBox, Proxmox, UniFi or Intune | **Integrations**. See [Integrations](Integrations). |

## Add one by hand

Only the hostname and the type are required. Everything else can be added later: IP address, MAC address, operating system and version, location, serial number, licence key or asset tag.

Locations you have used before are suggested as you type, so the same room or rack is spelled the same way everywhere.

## Import a CSV file

1. Open **Devices > Import > From a CSV file**.
2. Download the template, or use your own file with a header row.
3. Upload it. If your column names differ from the template, you match them to PrivateGlue's fields in the next step.

The known columns are `hostname`, `ip_address`, `mac_address`, `device_type`, `operating_system`, `os_version`, `serial_number`, `license_key` and `location`. Only `hostname` is required. The file can be UTF-8, UTF-16 or Latin-1 and at most 5 MB.

## Working with the list

- **Filter**: type in the filter box to search every column at once, or pick a type or location.
- **Sort**: click a column header. Click again to reverse.
- **Open**: click a row.
- **Edit, duplicate, delete**: the menu at the end of each row. Duplicate copies type, operating system and location, which helps with a batch of similar machines.
- **Delete several at once** (administrators): tick the boxes, then **Delete selected**. The box in the header selects every row the filter shows.

## The device page

A device page shows its details, the credentials and notes linked to it, and for some devices live information:

- **Proxmox VE hosts**: with a linked credential, **Fetch details** reads nodes, virtual machines and storage from the host. Set the operating system to "Proxmox VE" to get this.
- **Switches, routers, access points and firewalls**: if the device answers SNMP, you can view its interfaces and VLANs.

A device that came from an integration shows **Synced from** with a link to its record in the other system.

## Linking

Credentials and notes can be linked to devices, from either side. A linked credential or note shows on the device page, so everything about one machine is in one place.
