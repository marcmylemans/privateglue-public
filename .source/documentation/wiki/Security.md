# Security

PrivateGlue holds passwords and a map of your network. This page lists what it does to protect them and what is up to you.

## What PrivateGlue does

- Account passwords are stored as salted hashes. Stored credentials and integration tokens are encrypted, with a key kept apart from the database.
- There is no public sign-up. The first account is created at installation, every other account by an administrator.
- Sign-in attempts are limited per address and per username.
- Changing a password signs out every other session of that account.
- Two-factor sign-in with an authenticator app, which an administrator can require. See [Two-factor sign-in](Two-factor-sign-in).
- A record of who opened, copied and changed what. See [Activity](Activity-log).
- Uploaded files are only ever sent as downloads, so a file can never run as a page inside PrivateGlue.
- Pages only run PrivateGlue's own scripts, and notes are cleaned before they are shown.
- The container runs as an unprivileged user.
- It works offline and contacts no third party unless you turn on an integration.

## What you should do

1. **Use HTTPS** for anything reachable beyond your own network. See [Reverse proxy and HTTPS](Reverse-proxy-and-HTTPS).
2. **Back up, and protect the backups.** A backup zip contains the database and the key that decrypts it. See [Backup and restore](Backup-and-restore).
3. **Give accounts sparingly.** Every role can read every stored password.
4. **Turn on two-factor sign-in**, at least for administrators, for anything reachable beyond your own network.
5. **Keep it up to date.** See [Updating](Updating).
6. **Keep `SECRET_KEY` and `.env` private.**

## Things to know

- Two-factor sign-in is off until someone turns it on. There is no single sign-on.
- Attachments and notes are stored as they are, not encrypted. Secrets belong in a credential.
- The activity log is kept for 12 months and stores IP addresses and usernames.
- One install is one environment. To keep customers or teams apart, run one install for each.
- The app connects to addresses that its users enter: device addresses for the live Proxmox and SNMP details, integration addresses, and scan ranges when scanning from the server is on. On a network you share with others, limit what the container can reach.
- Scanning from the server is off unless you turn it on. Leave it off on a shared server.
- With the host-network compose file, PrivateGlue listens directly on the host. Protect the port.

## Reporting a problem

Please report a vulnerability privately, through a security advisory on the [GitHub repository](https://github.com/marcmylemans/privateglue-public), not in a public issue.
