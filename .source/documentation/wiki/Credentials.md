# Credentials

Credentials are the usernames and passwords that belong to your environment: the root account of a host, the admin login of a switch, a service account.

## Add a credential

1. Open **Credentials** and click **Add credential**.
2. Give it a title you will recognise, a username if there is one, and the password.
3. Optionally tick the devices it is used on.

**Generate** creates a strong random password of the length you choose.

## Using a credential

Open it to see the username and password. The password is hidden until you click the eye. The copy button copies it without showing it on screen.

A credential linked to a device also shows on that device's page.

## How passwords are protected

- Passwords are encrypted before they are stored. The key is kept apart from the database, in the `secretkey` Docker volume.
- Without that key the passwords cannot be read, by anyone. This is why the key must be part of your backups. See [Backup and restore](Backup-and-restore).
- A backup zip made in the app contains both the database and the key.

## Who can see them

Every account, including read-only, can read every stored password. See [Users and roles](Users-and-roles). PrivateGlue does not record who looked at which password.

## What it is not

PrivateGlue documents the credentials of your infrastructure next to the devices they belong to. It is not a personal password manager: it has no browser extension, no auto-fill and no sharing with people outside.
