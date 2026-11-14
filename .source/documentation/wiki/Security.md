# Security

PrivateGlue holds passwords and a map of your network. This page lists what it does to protect them and what is up to you.

## What PrivateGlue does

- Account passwords are stored as salted hashes. Stored credentials and integration tokens are encrypted, with a key kept apart from the database.
- There is no public sign-up. The first account is created at installation, every other account by an administrator.
- Sign-in attempts are limited per address and per username.
- Changing a password signs out every other session of that account.
- Pages only run PrivateGlue's own scripts, and notes are cleaned before they are shown.
- The container runs as an unprivileged user.
- It works offline and contacts no third party unless you turn on an integration.

## What you should do

1. **Use HTTPS** for anything reachable beyond your own network. See [Reverse proxy and HTTPS](Reverse-proxy-and-HTTPS).
2. **Back up, and protect the backups.** A backup zip contains the database and the key that decrypts it. See [Backup and restore](Backup-and-restore).
3. **Give accounts sparingly.** Every role can read every stored password.
4. **Keep it up to date.** See [Updating](Updating).
5. **Keep `SECRET_KEY` and `.env` private.**

## Things to know

- There is no two-factor sign-in.
- PrivateGlue does not record who viewed which password or who changed what.
- One install is one environment. To keep customers or teams apart, run one install for each.
- The app connects to addresses that its users enter: device addresses for the live Proxmox and SNMP details, integration addresses, and scan ranges when scanning from the server is on. On a network you share with others, limit what the container can reach.
- Scanning from the server is off unless you turn it on. Leave it off on a shared server.
- With the host-network compose file, PrivateGlue listens directly on the host. Protect the port.

## Reporting a problem

Please report a vulnerability privately, through a security advisory on the [GitHub repository](https://github.com/marcmylemans/privateglue-public), not in a public issue.
