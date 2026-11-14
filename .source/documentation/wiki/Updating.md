# Updating

This page is for Docker installs. Installed with the Proxmox VE script? Run `update` in the container, see [Install on Proxmox VE](Install-on-Proxmox).

## The short version

```bash
cd privateglue
docker compose pull
docker compose up -d
```

Your data stays where it is. The database is upgraded by itself when the new version starts, and nobody is signed out by an update.

## Before you update

Create a backup first: open **System & backups** in the app and click **Create backup**, then download the file. See [Backup and restore](Backup-and-restore). It is the one step that makes any update reversible.

## Keep the compose file current

New versions sometimes add settings, and the compose file is what passes settings into the container. Refresh it once in a while:

```bash
cp docker-compose.yml docker-compose.yml.old
curl -fsSL https://raw.githubusercontent.com/marcmylemans/privateglue-public/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

Your `.env` file and your data are not touched by this. If you changed the compose file by hand, compare it with the `.old` copy and redo your changes.

## Which version am I running?

The version is shown at the bottom of the menu and under **System & backups**.

## Following development builds

Set `PRIVATEGLUE_TAG=edge` in `.env` to run the newest build from the development branch. It gets new features first and is tested automatically, but it has not been through a release. For anything you rely on, stay on `latest`.

## Automatic updates

Tools such as Watchtower can pull new images for you. If you use one, make sure backups run too, and consider pinning a version (`PRIVATEGLUE_TAG=0.7`) so only fixes for that version arrive unattended.

## Going back to an older version

1. Set `PRIVATEGLUE_TAG` to the older version in `.env`.
2. `docker compose up -d`.

An older version may not understand a database that a newer version has upgraded. If it does not start cleanly, restore the backup you made before updating into a fresh install of the older version.
