# Integrations

Integrations connect PrivateGlue to other systems you run. They are found under **Integrations** in the menu, for administrators.

| Integration | What it does | Guide |
|---|---|---|
| NetBox | Imports devices and, if you want, virtual machines | [NetBox](Integration-NetBox) |
| Proxmox VE | Imports nodes, virtual machines and containers of a cluster or single host | [Proxmox VE](Integration-Proxmox-VE) |
| UniFi Network | Imports gateways, switches and access points, and optionally connected clients | [UniFi Network](Integration-UniFi-Network) |
| Microsoft Intune | Imports managed devices through Microsoft Graph | [Microsoft Intune](Integration-Microsoft-Intune) |
| GitHub notes sync | Pushes your notes to a GitHub repository, or pulls them from one | [GitHub notes sync](Integration-GitHub-notes-sync) |

Each guide explains how to create the token or app registration the integration needs, with the fewest permissions that work. The same guide opens inside PrivateGlue with the **Setup guide** button on an integration's page.

## How they all work

1. Open the integration and fill in its settings.
2. Tick **Turn this integration on** and click **Save**.
3. Click **Test connection**. It checks the saved settings and changes nothing.
4. Click **Sync now**. The sync runs in the background. Reload the page to see the result in the run history.
5. Optionally choose **Automatic sync** (every 15 minutes up to once a week). The default is manual only.

## What a device sync does and does not do

- It **never deletes** devices. A device that disappears from the other system stays in PrivateGlue until you remove it.
- By default it **only fills empty fields**. What you typed by hand stays. Each device integration has an "overwrite" option if the other system should win.
- It **does not create duplicates**. A device you added by hand is recognised by its serial number, MAC address or hostname, in that order, and linked.
- A synced device shows **Synced from** on its page, with a link to its record in the other system.

Imported more than you wanted, for example every UniFi client? On the device list, filter, tick the header checkbox and use **Delete selected**. Then narrow the integration's settings before the next sync.

## Tokens

Tokens and passwords you enter for an integration are stored encrypted, with the same key as your credentials, and are never shown again. Leave a token field empty when you save to keep the stored one.

## Turning scheduled syncs off

Set `INTEGRATIONS_SCHEDULER=off` in `.env` to stop every automatic sync. **Sync now** keeps working.
