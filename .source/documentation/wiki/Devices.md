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

### Open and connect

- **Open web interface** appears when a credential linked to the device has a web address. It opens that address in a new tab. See [Credentials](Credentials).
- **Copy SSH command** appears when the device has an IP address. It copies `ssh <username>@<ip>`, with the username of the first linked credential.

### Dates to watch

Warranties, support contracts, licences and certificates run out. Record their end dates under **Dates to watch** when you edit a device: a kind, an optional label, the date and an optional note.

- The device page lists them, soonest first. Red means the date has passed, amber means today or within 60 days.
- Those red and amber ones also show in **Running out soon** on the dashboard, the five most urgent first.
- A device can have 12 dates. Clearing a date removes that row when you save.
- Duplicating a device does not copy its dates.

### Attachments

Keep files with a device: a config export, the warranty PDF, a rack photo.

- Editors and administrators upload under **Attachments** on the device page. Everyone who can see the device can download. Only administrators delete.
- A file can be 5 MB and a device can have 20 files.
- A file always downloads. Nothing opens inside PrivateGlue, not even a PDF or an image.
- Files are part of backups, and they are deleted together with the device.
- Files are stored as they are, not encrypted, like notes. Put passwords and keys in a credential.

## Linking

Credentials and notes can be linked to devices, from either side. A linked credential or note shows on the device page, so everything about one machine is in one place.
