# PrivateGlue

**PrivateGlue** is a self-hosted web app for documenting devices, notes and credentials, so homelabbers and IT professionals keep everything about their environment in one place they control.

Good for:
- Homelab documentation: servers, VMs, switches, VLANs, services
- Freelancers and consultants managing client environments
- Small IT teams building a shared, private knowledge base

<!-- This file is maintained in the private source repo (public/README.md) and synced on each release. -->

## Features

- **Device inventory**: hostname, IP, MAC, OS, location and serial numbers, with filtering and CSV import
- **Markdown notes** with live preview, code highlighting, tags and device links
- **Encrypted credentials**, linked to devices, copied to the clipboard without showing them on screen, with an address to open, one-time codes, extra encrypted fields for SSH keys and API tokens, tags, and password age with reminders
- **Attachments and dates to watch**: files on devices and notes, and warranty, licence and certificate end dates with a dashboard reminder
- **Two-factor sign-in** with an authenticator app, and an **activity log** of who opened, copied and changed what
- **Search** across devices, notes (including their text) and credentials
- **Proxmox VE and SNMP**: live node, VM, container and storage details; switch interfaces and VLANs
- **Users and roles** (admin, editor, read-only), one-click backups and restore
- Light, dark and system themes; works fully offline (no CDN or third-party calls)

Screenshots: [privateglue.app](https://privateglue.app/#tour)

**Full guide:** installing, updating, backups, the network probe, integrations and troubleshooting are in the [documentation](https://privateglue.app/docs/). What each version brought: [What's new](https://privateglue.app/docs/changelog/).

## Quick start

You need Docker with Docker Compose.

```bash
mkdir privateglue && cd privateglue
curl -fsSL https://raw.githubusercontent.com/marcmylemans/privateglue-public/main/docker-compose.yml -o docker-compose.yml
echo "SECRET_KEY=$(openssl rand -hex 32)" > .env
docker compose up -d
```

Open [http://localhost:5000](http://localhost:5000) and create your admin account, or restore a backup.

### Proxmox VE, without Docker

In the shell of your Proxmox node:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/marcmylemans/privateglue-public/main/ct/privateglue.sh)"
```

This creates an LXC container and installs PrivateGlue in it. Details are in the [guide](https://privateglue.app/docs/install-on-proxmox/).

Using **Dockge** or **Portainer**? Paste `docker-compose.yml` as the stack and put `SECRET_KEY=...` in the stack's environment (`.env`). The compose file passes it into the container.

### Settings (`.env`)

| Variable | Required | Default | What it does |
|---|---|---|---|
| `SECRET_KEY` | yes | | Signs login sessions. Generate with `openssl rand -hex 32`. Keep it stable. |
| `PRIVATEGLUE_TAG` | no | `latest` | Image tag: `latest` (releases), a version like `0.7.0`, or `edge` (newest `main`) |
| `PRIVATEGLUE_PORT` | no | `5000` | Port on the host |
| `PUID` / `PGID` | no | `1000` | User and group that own the data folders |

### Data and backups

| Path | Contents |
|---|---|
| `./data` | SQLite database |
| `./notes` | Markdown notes |
| `./backups` | Backups created from the app |
| `secretkey` volume | Encryption key for stored credentials |

Without the encryption key, stored credentials can't be decrypted. The easiest safe backup is **Create backup** in the account menu: the zip contains the database, the key and all notes, and a fresh install can restore it.

### Updating

```bash
docker compose pull && docker compose up -d
```

Upgrading from an older version: the app now runs as an unprivileged user and fixes ownership of the data folders on start, so existing installs keep working. Make sure `.env` has a `SECRET_KEY` and remove any `curl` healthcheck from an old compose file (the image has its own).

## Changelog

See [CHANGELOG.md](.source/documentation/CHANGELOG.md) for all changes and versions.

## Support

If you like this project, consider [starring it on GitHub](https://github.com/marcmylemans/privateglue-public). For feedback, suggestions or bug reports, open an issue.

## License

MIT: free for personal and commercial use. See [LICENSE](LICENSE).
