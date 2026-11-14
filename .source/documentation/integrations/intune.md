# Microsoft Intune

Imports the devices that Microsoft Intune manages (Windows, macOS, iOS/iPadOS, Android and
Linux) into the PrivateGlue device list. It reads from Microsoft Graph with an app registration
in Microsoft Entra ID and only ever reads: nothing is changed in Intune, and nothing is deleted
in PrivateGlue.

Version 1 works with the global Microsoft cloud only (`login.microsoftonline.com` and
`graph.microsoft.com`). National clouds such as Microsoft 365 GCC High, DoD or the China cloud
operated by 21Vianet are not supported.

## What you need

- A tenant with an active Intune license (Graph's Intune API refuses tenants without one).
- An account that can create app registrations and grant admin consent for application
  permissions (Global Administrator or Privileged Role Administrator).
- Outbound HTTPS from the PrivateGlue container to `login.microsoftonline.com` and
  `graph.microsoft.com`.

## Set up the app registration

1. Open the Microsoft Entra admin center (entra.microsoft.com) and go to
   **Entra ID > App registrations > New registration**.
2. Name it something you will recognise later, for example `PrivateGlue Intune import`.
   Keep **Accounts in this organizational directory only**. Leave Redirect URI empty.
   Select **Register**.
3. On the **Overview** page, copy:
   - **Directory (tenant) ID**: goes into **Tenant ID**.
   - **Application (client) ID**: goes into **Application (client) ID**.
4. Go to **API permissions > Add a permission > Microsoft Graph > Application permissions**.
   Search for `DeviceManagementManagedDevices.Read.All`, tick it and select **Add permissions**.
   This is the least privilege that can list managed devices: it is read-only and cannot
   wipe, retire or change devices. You can remove the default delegated `User.Read`
   permission; the import does not use it.
5. Still on **API permissions**, select **Grant admin consent for <your tenant>** and confirm.
   The status column must show a green check for the permission. Without consent the sync
   fails with "Microsoft Graph denied access (HTTP 403)".
6. Go to **Certificates & secrets > Client secrets > New client secret**. Give it a
   description and pick an expiry. Select **Add**, then copy the **Value** straight away (it
   is shown only once). The Value goes into **Client secret**. Do not use the **Secret ID**.

### The client secret expires

Every client secret has an end date (at most 24 months). On that date the sync starts to fail
with: "Sign-in failed (AADSTS7000222): The client secret has expired." Put the date in your
calendar. To renew: create a new secret on the same app registration, paste the new Value in
PrivateGlue and save, then delete the old secret in Entra.

## Settings

| Setting | What it does |
| --- | --- |
| Tenant ID | Directory (tenant) ID (a GUID). Your `something.onmicrosoft.com` domain works too. Anything else is refused before a request is made. |
| Application (client) ID | The app registration's Application (client) ID (a GUID). |
| Client secret | The secret Value. Stored encrypted and never shown again; leave the field empty to keep the saved one. |
| Operating systems to import | All (default), Windows only, macOS only, Windows and macOS, or Mobile only (iOS/iPadOS and Android). Linux devices are only imported with "All". |
| Skip personally owned devices | Leaves out devices that Intune marks as personal (BYOD). Off by default. |
| Location label for imported devices | Optional text, for example `Office`, put in the Location field of imported devices. |
| Overwrite PrivateGlue values | Off (default): only empty fields are filled in, so what you typed by hand stays. On: Intune wins for name, serial number, MAC address, operating system, version and location. The device type is never overwritten, see below. |

**Test connection** signs in and reads one device. It answers "Connected to tenant ...,
permission OK" when the app registration, secret, permission and consent are all right.

## What is synced

| Intune (Graph `managedDevice`) | PrivateGlue |
| --- | --- |
| `deviceName` | Hostname |
| `serialNumber` | Serial number |
| `ethernetMacAddress`, else `wiFiMacAddress` | MAC address |
| `operatingSystem` | Operating system |
| `osVersion` | Version |
| `operatingSystem` and `model` | Type (see below) |
| the "Location label" setting | Location |
| `id` | Link to the Intune record, so a renamed device is found again |

Details:

- **Serial numbers that are placeholders** are ignored. Cheap or white-label hardware often
  reports values such as `0`, `Default string`, `To be filled by O.E.M.` or
  `SystemSerialNumber`. Because PrivateGlue matches an imported device to an existing one by
  serial number first, keeping those would glue unrelated devices together.
- **MAC addresses** of all zeros are ignored. Graph often leaves the Ethernet MAC empty in a
  device list, so most devices get their Wi-Fi MAC.
- **IP address** stays empty. Intune does not report a usable IP address for managed devices.
- **Device type**:
  - iOS: Phone, or Tablet when the model is an iPad. iPadOS: Tablet.
  - Android: Tablet when the model looks like one (for example `Galaxy Tab` or Samsung
    `SM-T`, `SM-P`, `SM-X` models), otherwise Phone.
  - Windows and Linux: VM for Hyper-V, VMware, VirtualBox, KVM/QEMU, Parallels and Windows 365
    Cloud PC models, otherwise **Laptop**.
  - macOS: Laptop for MacBooks, Desktop for iMac, Mac mini, Mac Pro and Mac Studio, otherwise
    Laptop.
  - Anything else: Other.

  The Graph v1.0 API does not say whether a Windows PC is a laptop or a desktop, so Windows
  PCs default to Laptop, which is what most Intune-managed Windows devices in a small
  business are. Because this is a guess, the type only fills an empty type: change it by hand
  once and the sync keeps your choice, also with "Overwrite" on.
- **Duplicates in Intune**: when a device was re-enrolled, Intune can hold an old and a new
  record with the same serial number. Both end up on the same PrivateGlue device. Records are
  applied oldest check-in first, so with "Overwrite" on the most recent one wins.
- **Matching**: an Intune device is found again by its Intune id. A device you created by hand
  first is adopted when the serial number, MAC address or hostname matches (in that order).

## What is not synced

- Nothing is written back to Intune, and devices removed from Intune are not removed from
  PrivateGlue. Delete them by hand when you retire hardware.
- Users, compliance state, encryption state, apps, IMEI, phone numbers and notes from Intune
  are not imported.
- There is no link to the device page in the Intune admin center yet (Microsoft does not
  document a stable URL for it).

## Limits and troubleshooting

- Devices are read 200 at a time, up to 250 pages (50,000 devices). If a tenant has more, the
  run ends with a warning and the rest is not imported.
- When Microsoft Graph throttles (HTTP 429), a wait of a few seconds is retried once. Longer
  waits stop the run with "Microsoft Graph is throttling requests"; the next run picks up
  again.
- If your network inspects HTTPS with its own certificate authority, give the container that
  CA (for example with the `REQUESTS_CA_BUNDLE` environment variable). Certificate checks
  cannot be turned off for this integration, because the client secret and access token go
  over these connections.

| Message | Fix |
| --- | --- |
| Sign-in failed (AADSTS90002): Tenant not found | Wrong Tenant ID. Copy the Directory (tenant) ID again. |
| Sign-in failed (AADSTS700016): Application (client) ID not found | Wrong Application (client) ID, or the app registration is in another tenant. |
| Sign-in failed (AADSTS7000215): Client secret rejected | You pasted the Secret ID instead of the Value, or the secret was deleted. |
| Sign-in failed (AADSTS7000222): The client secret has expired | Create a new client secret, see above. |
| Microsoft Graph denied access (HTTP 403) | Add the application permission `DeviceManagementManagedDevices.Read.All` and grant admin consent. Also check the tenant has an Intune license. |
