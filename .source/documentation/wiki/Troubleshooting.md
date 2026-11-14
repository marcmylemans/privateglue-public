# Troubleshooting

Start with the log. Most problems say what is wrong there:

```bash
docker compose ps
docker compose logs --tail 100
```

## It does not start

**"SECRET_KEY is not set"** or compose says a required variable is missing. The `.env` file next to `docker-compose.yml` needs a `SECRET_KEY`:

```bash
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env
docker compose up -d
```

In Dockge or Portainer, add `SECRET_KEY` to the stack's environment.

**"port is already allocated"**. Something else uses port 5000. Set another one in `.env`, for example `PRIVATEGLUE_PORT=8080`, and run `docker compose up -d`.

**The container is "unhealthy" or keeps restarting.** Read the log. If your compose file is old and contains a health check that uses `curl`, remove that block: the image has its own health check. Better still, download the current compose file (see [Updating](Updating)).

**Permission errors on the data folders.** Set `PUID` and `PGID` in `.env` to the user that owns the folders, then `docker compose up -d`. PrivateGlue fixes the ownership when it starts.

## Signing in

**"Too many requests".** Sign-in is limited to five attempts a minute per address. Wait a minute. If this hits everyone at once, you are behind a reverse proxy without `TRUSTED_PROXIES=1`. See [Reverse proxy and HTTPS](Reverse-proxy-and-HTTPS).

**Signing in works, then you are sent back to the login page.** `FORCE_HTTPS=true` is set but you opened the site over plain `http://`. Use the `https://` address, or remove the setting.

**The sign-up page says sign-up is closed.** That is intended. An administrator adds accounts. See [Users and roles](Users-and-roles).

**Forgotten password.** See [Users and roles](Users-and-roles).

## Credentials

**"Unable to decrypt" on a stored password.** The encryption key does not match the database. This happens when the `secretkey` volume was deleted (`docker compose down -v`), or when a database was copied to another install without the key. Restore a backup zip that was made in the app: it contains the matching key. See [Backup and restore](Backup-and-restore).

## Integrations and scanning

**The Integrations page is empty or missing.** Your image is older than the integrations. Run `docker compose pull && docker compose up -d`.

**Test connection fails with a certificate error.** The other system uses a self-signed certificate. Untick **Verify the TLS certificate** in that integration's settings, or give the system a trusted certificate.

**Test connection cannot connect.** The address must be reachable from inside the PrivateGlue container. `localhost` means the container itself, not your server: use the server's real address or name.

**A sync says it is already running for a long time.** A sync interrupted by a restart is released after an hour. Then start it again.

**"Scan from this server" says it is turned off.** Add `ALLOW_SERVER_SCAN=true` to `.env`. If it stays off, your compose file is older than the setting: download the current one.

**A scan finds devices but no MAC addresses.** That needs the host network. See [Network scan](Network-scan).

**A scan finds nothing.** Check the network you entered. From the server, test that the network is reachable at all: `docker compose exec privateglue ping -c 1 <an address in that network>`.

**The probe says the server refused the API key.** Copy the key again from **Devices > Discovered**. A new key may have been created since.

## A setting has no effect

The compose file passes settings into the container. An older compose file does not know newer settings. Download the current one, then `docker compose up -d`. See [Updating](Updating).

## Buttons or menus do nothing

Do a hard reload (Ctrl+F5, or Cmd+Shift+R on a Mac) so the browser loads the current scripts. If it stays that way, open the browser's developer console (F12), look for red messages and report them.

## Still stuck

Open an issue on the [GitHub repository](https://github.com/marcmylemans/privateglue-public/issues) with:

- the version (bottom of the menu),
- what you did and what happened,
- the relevant lines from `docker compose logs`.

Leave out your `SECRET_KEY`, tokens and passwords.
