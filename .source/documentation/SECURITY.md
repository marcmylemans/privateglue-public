# Security notes

Last reviewed: 2026-11-14.

## What the app does for you

- Passwords for accounts are stored as salted hashes. Stored credentials and integration
  tokens are encrypted with `secret.key` (Fernet).
- Every form is protected against cross-site request forgery. Notes are sanitised before
  they are shown, and a Content-Security-Policy stops injected script from running.
- Sign-up is closed after the first account. Logins are rate limited per address and per
  username. Changing a password signs out all other sessions of that account.
- Two-factor sign-in (TOTP) with recovery codes. An admin can require it for admins or for
  everyone. The secret is encrypted, recovery codes are stored as salted hashes, a code works
  once, and the password alone gives access to nothing for an account that has it on.
- An activity log records who opened a credential, showed or copied a secret, changed or
  deleted something, signed in or failed to. No password, code or key is ever written to it.
- One-time code secrets, extra fields and previous passwords on a credential are encrypted
  the same way as its password.
- Attachments are stored under a random name and only ever sent as a download
  (`Content-Disposition: attachment`, `application/octet-stream`, `nosniff`), so an uploaded
  HTML or SVG file cannot run script on the app's origin.
- An address on a credential only becomes a link for `https`, `http`, `ssh` and `rdp`.
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

"Scan from this server" (Devices > Discovered) is off by default. An administrator turns it
on and off in the app; the change is written to the log with the account that made it. When
on, administrators can make the server ping and connect to addresses in private ranges, and
ask the devices that answer for their name (DNS, NetBIOS on UDP 137, mDNS on UDP 5353). Names
reported by devices are checked before they are shown or stored. Only
turn it on where every administrator may look around the network the server is in.

On a hosted or shared server, set `ALLOW_SERVER_SCAN=never`. That keeps it off and removes
the switch, so no account in the app can turn it on. `ALLOW_SERVER_SCAN=true` keeps it on.

`docker-compose.host.yml` puts the container on the host network. The app then listens on
every address of the host, without Docker's port mapping in between: protect the port with
the host firewall or a reverse proxy.

## Known limits

These are not fixed in the app today. They matter most when you run it for other people.

- **No single sign-on.** Two-factor sign-in is off until a user turns it on or an admin
  requires it.
- **The activity log can be read but not sealed.** Someone with access to the database file
  can change it. It is kept for 12 months and stores IP addresses and the username typed at
  a failed sign-in.
- **Attachments and notes are not encrypted at rest.**
- **A lone admin who loses both phone and recovery codes cannot be reset from inside the
  app.** Keep a second admin account.
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
