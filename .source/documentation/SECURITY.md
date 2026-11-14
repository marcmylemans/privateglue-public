# Security notes

Last reviewed: 2026-11-14.

## What the app does for you

- Passwords for accounts are stored as salted hashes. Stored credentials and integration
  tokens are encrypted with `secret.key` (Fernet).
- Every form is protected against cross-site request forgery. Notes are sanitised before
  they are shown, and a Content-Security-Policy stops injected script from running.
- Sign-up is closed after the first account. Logins are rate limited per address and per
  username. Changing a password signs out all other sessions of that account.
- The container runs as an unprivileged user and refuses to start without `SECRET_KEY`.

## What you have to do when it is reachable from the internet

1. Put it behind a reverse proxy with HTTPS and set `FORCE_HTTPS=true` and `TRUSTED_PROXIES=1`.
2. Keep `secret.key` (the `secretkey` volume) backed up separately. Without it, stored
   passwords cannot be read. With it and a copy of the database, they all can.
3. A backup zip contains the database **and** `secret.key`. Treat the `backups` folder and
   every downloaded backup like a password export.
4. Give accounts only to people who may see every stored password. All roles can read them.
5. Keep the image up to date.

## The network probe

The [probe](https://github.com/marcmylemans/PrivateGlue-Probe) sends discovered devices to
`/api/discovered-devices` with an API key. The key only allows replacing the list of
discovered devices; it cannot read anything, and nothing reaches the inventory until an
editor imports it. Administrators see the key under Devices > Discovered and can replace it
there, which blocks the old key at once. Let the probe talk to the server over HTTPS.

## Scanning from the server

"Scan from this server" (Devices > Discovered) is off by default and is turned on with
`ALLOW_SERVER_SCAN=true`. When on, administrators can make the server ping and connect to
addresses in private ranges. Only turn it on where every administrator may look around the
network the server is in. Leave it off on a hosted or shared server.

`docker-compose.host.yml` puts the container on the host network. The app then listens on
every address of the host, without Docker's port mapping in between: protect the port with
the host firewall or a reverse proxy.

## Known limits

These are not fixed in the app today. They matter most when you run it for other people.

- **No two-factor sign-in** and no single sign-on.
- **No audit log**: the app does not record who viewed which password or who changed what.
- **One environment per install.** There are no separate customers or teams inside one
  install. Run one container with its own data per customer.
- **The app makes outbound connections to addresses its users enter**: SNMP and the Proxmox
  fetch use a device's address (any signed-in user can trigger them), integrations use the
  address an admin configures. On a shared network this lets a user reach hosts next to the
  container. Restrict what the container can reach at network level.
- **The per-device Proxmox fetch does not verify the TLS certificate** and signs in with a
  stored username and password. Prefer the Proxmox VE integration, which uses a read-only
  API token and verifies certificates by default.
- **Rate limits are kept in memory per worker process.** They slow guessing down but are not
  exact. Set `RATELIMIT_STORAGE_URI` to a Redis address for exact limits.
- **Device licence keys are stored unencrypted** in the database, unlike credentials.
- **Backups are not encrypted.**

## Reporting a problem

Open a private security advisory on the GitHub repository, or contact the maintainer directly.
Please do not open a public issue for a vulnerability.
