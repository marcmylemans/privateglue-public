# Installation

This page is the Docker install. On a Proxmox VE host you can also run PrivateGlue in its own container without Docker: see [Install on Proxmox VE](Install-on-Proxmox).

## What you need

- A machine with Docker and the Docker Compose plugin (`docker compose version` should print a version).
- A little disk space for the image and your data. PrivateGlue is small.

## Install

```bash
mkdir privateglue && cd privateglue
curl -fsSL https://raw.githubusercontent.com/marcmylemans/privateglue-public/main/docker-compose.yml -o docker-compose.yml
echo "SECRET_KEY=$(openssl rand -hex 32)" > .env
docker compose up -d
```

Open `http://<address of the machine>:5000`. The setup screen lets you create the first account, which becomes the administrator, or restore a backup from another install.

That is all. The four commands do this:

1. Make a folder that will hold the compose file, your settings and your data.
2. Download the compose file.
3. Create the settings file `.env` with a random `SECRET_KEY`. PrivateGlue refuses to start without one.
4. Download the image and start the container.

## Where your data lives

Everything is inside the folder you created, except the encryption key:

| Location | Contents |
|---|---|
| `./data` | The database |
| `./notes` | Your notes, as Markdown files |
| `./backups` | Backups you create from the app |
| Docker volume `secretkey` | The key that encrypts stored passwords |

**The encryption key matters.** Without it, stored passwords cannot be read. `docker compose down -v` deletes that volume. Never use `-v` unless you mean to wipe the install. See [Backup and restore](Backup-and-restore).

## Dockge or Portainer

Paste the contents of `docker-compose.yml` as a new stack and add `SECRET_KEY=<a long random value>` to the stack's environment. The compose file passes it into the container.

## Which version you get

The compose file uses the `latest` image, which is the newest release. To choose another, set `PRIVATEGLUE_TAG` in `.env`:

| Tag | What it is |
|---|---|
| `latest` | Newest release (default) |
| `0.7.0`, `0.7` | A fixed version |
| `edge` | Newest development build. Can change daily. |

## Running on the host network

The default setup puts the container on Docker's own network, which is right for most installs. If you want to scan your network from PrivateGlue and see MAC addresses, use the host-network compose file instead. See [Network scan](Network-scan).

## Next steps

- [Configuration](Configuration) for the other settings.
- [Reverse proxy and HTTPS](Reverse-proxy-and-HTTPS) before you make it reachable from outside your network.
- [Users and roles](Users-and-roles) to add your colleagues.
