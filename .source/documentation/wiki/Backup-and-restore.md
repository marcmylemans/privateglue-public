# Backup and restore

## What a backup contains

A backup is one zip file with:

- the database (devices, credentials, accounts, integration settings),
- the encryption key that protects stored passwords,
- all notes,
- the files attached to devices and notes.

The database also holds the activity log and everyone's two-factor sign-in, so those come back with a restore.

**Treat a backup like a password export.** It holds the encrypted passwords and the key to read them. Store it somewhere only you can reach.

## Create a backup

1. Sign in as an administrator.
2. Open **System & backups**.
3. Click **Create backup**.
4. Download the file from the list and store it off the server.

Backups are also kept in the `./backups` folder next to your compose file. That folder is on the same disk as your data, so it does not protect you against losing the server. Copy backups elsewhere.

## Restore a backup

A backup is restored into a **fresh install**, from the setup screen. It replaces everything, so it is not offered once an install has accounts.

1. Install PrivateGlue in a new folder. See [Installation](Installation). Do not create an account yet.
2. Open PrivateGlue. The setup screen offers **restore a backup**.
3. Upload your backup zip and click **Restore**. Alternatively, copy the zip into the new install's `./backups` folder before opening the page: the setup screen then offers **Restore detected backup**.
4. PrivateGlue shows **Backup restored** and restarts by itself to load the restored database and encryption key. That takes a few seconds, then the sign-in page opens. Sign in with an account from the backup.

The container or service keeps running during this; only the app inside it reloads. If the page instead asks you to restart, do that by hand: `docker compose restart`, or `systemctl restart privateglue` on a Proxmox install.

## Move to another server

Moving is a backup on the old server and a restore on the new one, exactly as above. Afterwards, check that a stored password opens: that proves the encryption key came along.

## Backing up the folders instead

You can also copy the install folder (`data`, `notes`, `backups`) with your normal backup tool. If you do, back up the `secretkey` Docker volume as well. The folders without the key give you everything except readable passwords.

To copy the key out of the volume:

```bash
docker compose cp privateglue:/app/secret/secret.key ./secret.key.backup
```

Keep that file as safe as a backup zip.

## What is not in a backup

- The network probe's API key. A restored install creates a new one. Copy it to your probes again (see [Network scan](Network-scan)).
- The list of discovered devices that you have not imported yet.
- Your `.env` file. Keep a copy of it with your backups.
