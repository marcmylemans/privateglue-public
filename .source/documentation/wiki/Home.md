# PrivateGlue user guide

PrivateGlue is a self-hosted web app for documenting your IT environment: devices, notes and credentials in one place that you control. This guide covers installing it, keeping it up to date and using each part.

## Start here

| I want to... | Page |
|---|---|
| Install PrivateGlue with Docker | [Installation](Installation) |
| Install PrivateGlue on Proxmox VE, without Docker | [Install on Proxmox VE](Install-on-Proxmox) |
| Change a setting (port, HTTPS, user id) | [Configuration](Configuration) |
| Update to a newer version | [Updating](Updating) |
| Back up or move my data | [Backup and restore](Backup-and-restore) |
| Put it behind a reverse proxy with HTTPS | [Reverse proxy and HTTPS](Reverse-proxy-and-HTTPS) |
| Fix a problem | [Troubleshooting](Troubleshooting) |

## Using PrivateGlue

| Topic | Page |
|---|---|
| Accounts and what each role can do | [Users and roles](Users-and-roles) |
| Adding and managing devices | [Devices](Devices) |
| Finding devices on your network | [Network scan](Network-scan) |
| Pulling devices from NetBox, Proxmox, UniFi or Intune, and syncing notes with GitHub | [Integrations](Integrations) |
| Writing documentation | [Notes](Notes) |
| Storing passwords | [Credentials](Credentials) |
| What to think about before exposing it to the internet | [Security](Security) |

## Good to know

- PrivateGlue runs as one Docker container with a SQLite database. There is nothing else to install. On Proxmox VE it can also run in its own LXC container without Docker.
- It works fully offline. It makes no calls to third parties unless you turn on an integration.
- Every account, including read-only ones, can read stored passwords. Only give accounts to people you would hand those passwords to.
- This guide describes the latest release. The `edge` image can be ahead of it.
