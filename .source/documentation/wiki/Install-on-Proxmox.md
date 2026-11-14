# Install on Proxmox VE

On a Proxmox VE host you can run PrivateGlue in its own LXC container, without Docker. One command creates the container and installs everything in it, the same way the Proxmox VE community scripts work (it uses their engine).

This route is new. If something does not work, please [open an issue](https://github.com/marcmylemans/privateglue-public/issues) with the output of the script.

## Install

Open the **Shell** of your Proxmox node (not a container or VM) and run:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/marcmylemans/privateglue-public/main/ct/privateglue.sh)"
```

The script asks whether you want the default settings or the advanced ones. The defaults are fine for most setups:

| Setting | Default |
|---|---|
| Operating system | Debian 13 |
| Container type | Unprivileged |
| CPU / memory / disk | 1 core, 1 GB, 4 GB |
| Network | DHCP on your default bridge |

When it finishes it prints the address, for example `http://192.168.1.50:5000`. Open it soon: the first visitor creates the administrator account.

As with any script you run as root on a host, it is fair to read it first. It is short: [ct/privateglue.sh](https://github.com/marcmylemans/privateglue-public/blob/main/ct/privateglue.sh) creates the container and [install/privateglue-install.sh](https://github.com/marcmylemans/privateglue-public/blob/main/install/privateglue-install.sh) runs inside it.

## What it sets up

| Location in the container | Contents |
|---|---|
| `/opt/privateglue` | The app and its Python environment |
| `/opt/privateglue/data` | The database |
| `/opt/privateglue/notes` | Your notes, as Markdown files |
| `/opt/privateglue/backups` | Backups you create from the app |
| `/opt/privateglue/secret` | The key that encrypts stored passwords |
| `/etc/privateglue/privateglue.env` | Settings, including the generated `SECRET_KEY` |

PrivateGlue runs as a systemd service named `privateglue`, under its own user without administrator rights.

```bash
systemctl status privateglue      # is it running?
journalctl -u privateglue -e      # the log
systemctl restart privateglue     # restart, for example after changing a setting
```

## Change a setting

Edit `/etc/privateglue/privateglue.env` in the container, then restart the service. The settings are the same as on the [Configuration](Configuration) page, except the ones that only make sense for Docker (`PRIVATEGLUE_TAG`, `PRIVATEGLUE_PORT`, `PUID`, `PGID`).

```bash
nano /etc/privateglue/privateglue.env
systemctl restart privateglue
```

Keep `SECRET_KEY`, `PRIVATEGLUE_HOME` and `PYTHONPATH` as they are.

## Update

Create a backup in the app first (**System & backups**, **Create backup**). Then open the console of the container and run:

```bash
update
```

It checks for a newer release, replaces the app and keeps `data`, `notes`, `backups` and `secret`. The database is upgraded by itself when the new version starts. If you are already on the newest release it says so and changes nothing.

## Back up

Two things work, and they go well together:

- **Backups from the app**, as described in [Backup and restore](Backup-and-restore). Download them, so a copy lives outside the container.
- **Proxmox backups of the whole container** (vzdump or Proxmox Backup Server). These include the database, the notes and the encryption key in one go.

## Scanning the network

The container sits directly on your network, so [scanning from the server](Network-scan) sees the real devices, MAC addresses included. Switch it on by setting `ALLOW_SERVER_SCAN=true` in the settings file and restarting the service.

## Moving from Docker to the container

1. In the Docker install: create a backup in the app and download it.
2. Install the container as above.
3. On the setup screen of the new install, upload the file under **restore a backup** and click **Restore**.

Afterwards, check that a stored password opens: that proves the encryption key came along.

## Remove

Stop and delete the container in the Proxmox interface. Everything PrivateGlue installed lives inside it.
