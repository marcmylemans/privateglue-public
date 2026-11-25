# UniFi Network

Imports your UniFi gateways, switches and access points into the PrivateGlue device list, and
optionally the clients connected to your network. It is a one-way, read-only import: PrivateGlue
only reads from UniFi and never changes anything there.

## Two ways to sign in

Which one you use depends on what runs your UniFi Network:

| Your UniFi | Sign in with |
|-|-|
| A UniFi OS console: Cloud Gateway, Dream Machine, Cloud Key, or the self-hosted **UniFi OS Server** | **API key** (or username and password) |
| The self-hosted **UniFi Network Server** (the classic controller, often on port 8443) | **Username and password**. It cannot create API keys, also not in its newest version. |

Not sure which you have? If UniFi Network has no **Integrations** page under Settings > Control
Plane, use username and password.

## Requirements

- For an API key: UniFi Network 9.0 or newer on UniFi OS. On a Cloud Gateway this means UniFi OS
  4.1.9 or newer.
- For username and password: any UniFi Network version.
- PrivateGlue must be able to reach the console over HTTPS: port 443 on a UniFi OS console, 8443
  on a self-hosted Network Server, 11443 on a UniFi OS Server.

## Sign in with username and password

Create an account for PrivateGlue only. Do not use your own.

1. In UniFi, open the admins page (**Admins & Users** on UniFi OS, **Settings > Admins** on a
   Network Server; the name differs a little between versions).
2. Add an admin with a username and password. Choose a **local** account: turn on "Restrict to
   local access only", or leave "Remote access" off. An account that signs in through UI.com
   asks for a two-factor code and cannot be used.
3. Give it the **View Only** role for Network. PrivateGlue only reads.
4. In PrivateGlue, set **Sign in with** to "Username and password" and fill in both. The page
   then shows the username and password fields in place of the API key field.

PrivateGlue signs in at the start of each sync, reads, and signs out again. The password is
stored encrypted and never shown again after saving. Because the account is view-only, this is
the safer choice of the two: an API key can change things, this account cannot.

## Sign in with an API key

1. Open UniFi Network on your console.
2. Go to **Settings > Control Plane > Integrations**.
3. Create an API key, give it a name such as `privateglue`, and copy it. It is shown only once.
4. Paste it in the **API key** field in PrivateGlue.

The UniFi documentation does not offer a read-only key: assume a key can do everything the API
allows, including changes. PrivateGlue only sends read requests (GET), but treat the key like
an admin password.
Use a key for PrivateGlue only, so you can delete it on its own if you stop using the
integration. PrivateGlue stores it encrypted and never shows it again after saving.

## Settings

| Setting | Default | What it does |
|-|-|-|
| Console address | (required) | The address of the console, for example `https://192.168.1.1`, or `https://unifi.lan:8443` for a self-hosted Network server. No path needed. |
| Sign in with | API key | API key, or username and password. See "Two ways to sign in". |
| API key | empty | Only for sign-in with an API key. Leave empty when editing to keep the saved key. |
| Username | empty | Only for sign-in with username and password. |
| Password | empty | Only for sign-in with username and password. Leave empty when editing to keep the saved password. |
| Verify the TLS certificate | on | UniFi consoles ship with a self-signed certificate, so the check fails out of the box. Either install a trusted certificate on the console, or turn this off. With it off the connection is still encrypted, but PrivateGlue cannot tell it is talking to your real console. |
| Site name | empty | Only import this site. Use the name you see in UniFi (for example `Default`). Empty imports every site on the console. |
| Import UniFi devices | on | Imports gateways, switches and access points that are adopted in UniFi Network. |
| Import clients | off | Also imports connected clients (computers, servers, printers and so on). |
| Wired clients only | on | With client import on, only wired clients are imported. See "Why Wi-Fi clients are off by default". |
| Overwrite PrivateGlue values | off | Off: a sync only fills in fields that are empty in PrivateGlue, so your own edits stay. On: values from UniFi replace what is in PrivateGlue. |

**Test connection** lists the sites and shows the UniFi Network version, for example
"Connected to UniFi Network 10.1.68, 2 sites found". When the site name you filled in does not
exist, it tells you which sites do.

## What is imported

### UniFi devices

| PrivateGlue field | From UniFi |
|-|-|
| Hostname | Device name. A device without a name gets its model plus the last 6 characters of its MAC address, for example `U7-Pro-26c6ca`. |
| MAC address | MAC address |
| IP address | IP address |
| Type | Gateway: **Router**. Access point: **Access point**. Switch: **Switch**. Left empty when UniFi does not say. |
| Operating system | `UniFi` with the model code, for example `UniFi (U6-Pro)` |
| Version | Firmware version |
| Location | Site name |

A gateway (Dream Machine, Cloud Gateway, UXG) is filed as **Router**, not Firewall: UniFi itself
calls these gateways and routers, and it keeps a home-made firewall appliance (OPNsense,
pfSense) easy to tell apart in the list. If you prefer Firewall, change the type by hand once:
with overwrite off, the sync keeps your choice. Gateways often also have switch ports or a
radio, and in-wall access points have switch ports; the type follows the main role (gateway,
then access point, then switch).

### Clients

| PrivateGlue field | From UniFi |
|-|-|
| Hostname | Client name, or its hostname when it has no name |
| MAC address | MAC address |
| IP address | IP address |
| Location | Site name |

The type stays empty: UniFi does not give a reliable device type for clients. Set it by hand.

A client without a name or hostname is not imported. UniFi shows the MAC address as the name
of a client it knows nothing about, and a device list full of MAC addresses helps nobody. Give
the client a name in UniFi (or set a hostname on the device) and the next sync picks it up.
The run history shows how many clients were ignored this way.

VPN and Teleport connections are never imported: they are sessions, not devices.

### Why Wi-Fi clients are off by default

Phones, tablets and laptops use a different random ("private") MAC address per Wi-Fi network,
and some change it regularly. Every change would look like a new device. Add guest devices and
visitors' phones and the device list fills up quickly. Wired clients (servers, printers, NAS,
desktops) are stable, so they are the useful ones to document. Turn "Wired clients only" off if
you want Wi-Fi clients too.

## How matching works

- Each UniFi device is remembered by its UniFi id. A renamed device is updated, not duplicated.
- Each client is remembered by its MAC address, because client ids in UniFi can change.
- A device you already entered by hand is adopted when its serial number, MAC address or
  hostname matches, so you do not get duplicates.
- Devices removed from UniFi are not deleted from PrivateGlue. Imports never delete anything.

## Not synced

- Serial numbers (the API does not provide them), port and radio details, statistics, uplinks
  and topology.
- Networks, VLANs, Wi-Fi networks and firewall rules.
- UniFi Protect, Access and Talk devices (only UniFi Network devices are in this API).
- A link back to the device page in UniFi: PrivateGlue does not build one, because the console
  URL format is not documented.

## Limits

- Lists are read 200 records at a time (the API maximum), up to 100 pages per list, which is
  20 000 devices or clients per site. Beyond that the run stops reading that list and reports
  it in the run history.
- Clients are only the ones connected at the moment of the sync. A server that is switched off
  during the sync is not imported that time; it is not removed either.
- The address is tried under `/proxy/network/integration/v1` (UniFi OS consoles) and then under
  `/integration/v1` (self-hosted Network server). If your setup uses another path, put the full
  path in the console address, for example `https://host/proxy/network`.

## Troubleshooting

- **Rejected the credentials (HTTP 401)**: the API key is wrong or was deleted. Create a new one.
- **There is no Integrations page, so no API key can be made**: you run the self-hosted UniFi
  Network Server. Set **Sign in with** to "Username and password".
- **UniFi did not accept this username and password**: check both, and that it is a local account.
  An account that signs in through UI.com does not work here.
- **This UniFi account asks for a two-factor code**: use a local account without two-factor
  sign-in, made for PrivateGlue only.
- **UniFi is refusing sign-ins for a moment**: too many failed attempts. Wait a few minutes.
- **Could not verify the TLS certificate**: the console uses its self-signed certificate. Turn
  off "Verify the TLS certificate" or install a trusted certificate.
- **No UniFi Network API found**: the address is not a UniFi console, or UniFi Network is older
  than 9.0. Update UniFi Network.
- **Site "..." was not found**: the message lists the site names that exist. Use one of them,
  or leave the field empty.
