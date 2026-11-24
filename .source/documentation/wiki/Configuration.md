# Configuration

Settings go in the `.env` file next to `docker-compose.yml`, one `NAME=value` per line. After a change, apply it with:

```bash
docker compose up -d
```

Installed with the Proxmox VE script? The same settings live in `/etc/privateglue/privateglue.env`, see [Install on Proxmox VE](Install-on-Proxmox).

## Settings

| Setting | Default | What it does |
|---|---|---|
| `SECRET_KEY` | none, required | Signs login sessions. Use a long random value (`openssl rand -hex 32`) and keep it the same. Changing it signs everyone out. |
| `PRIVATEGLUE_TAG` | `latest` | Which image to run. See [Installation](Installation). |
| `PRIVATEGLUE_PORT` | `5000` | The port PrivateGlue is reachable on. |
| `PUID` / `PGID` | `1000` | The user and group id that own the data folders. Set these to match a user on the host if you want to edit notes there. |
| `FORCE_HTTPS` | `false` | Set to `true` when PrivateGlue is only reached over HTTPS. Marks cookies as secure. |
| `TRUSTED_PROXIES` | `0` | The number of reverse proxies in front of PrivateGlue, usually `1`. See [Reverse proxy and HTTPS](Reverse-proxy-and-HTTPS). |
| `ALLOW_SERVER_SCAN` | `false` | Overrules the switch in the app for scanning from the server. `false`: an administrator decides in the app (off until turned on). `true`: always on. `never`: always off and the switch is hidden, for a server you share with others. See [Network scan](Network-scan). |
| `INTEGRATIONS_SCHEDULER` | `on` | Set to `off` to stop integrations from syncing on a schedule. Manual syncs keep working. |
| `PRIVATEGLUE_HOME` | `/app` | Only for installs without Docker: the folder that holds `data`, `notes`, `backups` and `secret`. The Proxmox VE script sets it to `/opt/privateglue`. Leave it alone in Docker, where the compose file decides where data lives. |

## Example

```ini
SECRET_KEY=3f9c...your-own-random-value
PRIVATEGLUE_PORT=8080
FORCE_HTTPS=true
TRUSTED_PROXIES=1
```

## If a setting seems to be ignored

The compose file decides which settings reach the container. An older copy of `docker-compose.yml` does not know newer settings. Download the current file again (see [Updating](Updating)) and run `docker compose up -d`.

## Checking that it runs

```bash
docker compose ps          # the state should be "healthy"
docker compose logs -f     # live log output, stop with Ctrl+C
```
