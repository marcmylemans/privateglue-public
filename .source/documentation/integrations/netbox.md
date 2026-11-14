# NetBox

Imports devices, and if you want virtual machines too, from [NetBox](https://netboxlabs.com/docs/netbox/)
into the PrivateGlue device list. It is one way: PrivateGlue only reads from NetBox and never
changes anything there.

Written and tested against the API of NetBox 3.7 up to 4.5 and the current development
version. Older versions are not supported.

## What you need in NetBox

A read-only API token. The cleanest way:

1. Create a separate user in NetBox, for example `privateglue`. It does not need staff or
   superuser rights.
2. Give it an object permission with only the **View** action on:
   - **DCIM > Device**
   - **Virtualization > Virtual machine** (only if you import virtual machines)

   You can add constraints to the permission if PrivateGlue should only see part of your
   NetBox.
3. Log in as that user (or as an admin, under Admin > API Tokens) and create a token for it.
   Leave **Write enabled** off. Set **Allowed IPs** to the address of your PrivateGlue host if
   you want to be strict.
4. Copy the token straight away. NetBox 4.5 and later show a new-style token only once.

### Which token formats work

- **v2 tokens** (NetBox 4.5 and later, the default there) look like
  `nbt_<key>.<secret>`. Paste the whole value, starting with `nbt_`. PrivateGlue sends it as
  `Authorization: Bearer ...`.
- **v1 tokens** (NetBox up to 4.4, still accepted but deprecated in newer versions) are 40
  characters of letters and digits. PrivateGlue sends them as `Authorization: Token ...`.

PrivateGlue picks the format from the `nbt_` prefix. If you paste the token with `Bearer `
or `Token ` already in front, that is used as is.

## Settings

| Setting | Default | What it does |
|---|---|---|
| NetBox address | (required) | The address you open NetBox on, for example `https://netbox.example.lan`. Without `/api`; if you add it anyway it is removed. |
| API token | (required) | The token from above. Stored encrypted, never shown again. Leave the field empty when saving to keep the saved token. |
| Verify the TLS certificate | on | Turn off only when NetBox uses a self-signed certificate. |
| Import virtual machines too | off | Also imports NetBox virtual machines. They get the type VM. |
| Only import objects with status Active | on | Skips planned, staged, offline, decommissioning and other statuses. |
| Only these sites | empty | Site slugs, comma separated, for example `hq, branch-1`. Objects in any of these sites are imported. Empty means all sites. |
| Only objects with one of these tags | empty | Tag slugs, comma separated. An object with at least one of the tags is imported. Empty means no tag filter. |
| Overwrite PrivateGlue values with NetBox values | off | Off: a sync only fills in fields that are empty in PrivateGlue, so what you typed by hand stays. On: NetBox wins for every field where it has a value. |

Site and tag filters work together: with both filled in, an object must be in one of the
sites and have one of the tags. Use slugs, not display names (you find the slug on the
site or tag page in NetBox).

**Test connection** reads `/api/status/` and lists one device, so it checks the address,
the certificate and the token in one go. It answers for example
"Connected to NetBox 4.5.1, 42 devices visible to this token".

## What is imported

| PrivateGlue field | Taken from NetBox |
|---|---|
| Hostname | Name. A device without a name gets its display value (for example "PowerEdge R640 (12)"). A virtual machine without a name is skipped and listed as an error. |
| IP address | Primary IPv4 address, otherwise the primary IPv6 address, without the prefix length. |
| MAC address | Only when NetBox puts a MAC address on the device or VM record itself. Current NetBox versions keep MAC addresses on interfaces, which this integration does not read, so this normally stays empty. |
| Serial number | Serial. Virtual machines have one from NetBox 4.1. |
| Type | Devices: the role, translated to a PrivateGlue type when the role name or slug clearly says so (switch, router, firewall, server, access point, NAS, printer, camera, desktop, laptop, phone, tablet, IoT). Otherwise the role name as it is. Virtual machines: VM. |
| Operating system | Platform name. |
| Location | Site, location and rack, as "Site / Location / Rack", cut to 100 characters. A virtual machine without a site gets its cluster name. |

Every imported device shows a link back to its page in NetBox. PrivateGlue remembers the
NetBox id (`device:<id>` or `vm:<id>`), so a device renamed in NetBox is updated instead of
duplicated. A device you entered by hand before the first sync is taken over when its serial
number, MAC address or hostname matches.

## What is not imported

- Interfaces, MAC addresses on interfaces, cables, IP prefixes, VLANs, circuits, tenants,
  contacts and custom fields.
- Changes in the other direction: nothing is ever written to NetBox.
- Deletions: a device removed in NetBox, or one that no longer matches the filters, stays in
  PrivateGlue. Delete it by hand if you no longer need it.
- Credentials, license keys, OS version and notes stay PrivateGlue-only.

## Limits

- Pages of 200 objects are read, up to 500 pages per list (100,000 objects). A bigger
  NetBox stops the sync with a message asking you to narrow it down with the site or tag
  filter.
- With several tags, NetBox is asked once per tag, so a sync with many tags takes longer.
- Every request has a 20 second timeout.
- PrivateGlue pages through NetBox by offset on the address you configured, instead of
  following the "next" links NetBox sends. NetBox behind a reverse proxy often builds those
  links with the wrong scheme or host name.

## Troubleshooting

- **"NetBox rejected the credentials (HTTP 403)"**: the token is wrong, disabled, expired,
  limited to other IP addresses, or the user cannot view devices.
- **"Could not verify the TLS certificate of NetBox"**: use a trusted certificate or turn off
  certificate verification.
- **"NetBox answered 404 Not Found"**: check the address. If NetBox runs under a sub-path,
  include it, for example `https://example.lan/netbox`.
- **Fewer devices than expected**: check "Only import objects with status Active" and the
  site and tag filters, and that the token's user may view all of them.
