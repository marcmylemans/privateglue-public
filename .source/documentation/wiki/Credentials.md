# Credentials

Credentials are the usernames and passwords that belong to your environment: the root account of a host, the admin login of a switch, a service account.

## Add a credential

1. Open **Credentials** and click **Add credential**.
2. Give it a title you will recognise, a username if there is one, and the password.
3. Optionally tick the devices it is used on.

**Generate** creates a strong random password of the length you choose.

Everything below is optional. A credential with only a title and a password works as before.

## Using a credential

Open it to see the username and password. The password is hidden until you click the eye. The copy button copies it without showing it on screen.

A credential linked to a device also shows on that device's page.

## Address

Fill in **Address** with where the login is used, for example `https://10.0.10.11:8006`. On the credential page **Open** opens it in a new tab and the copy button copies it.

- Tick a device under **Used on devices** and its addresses are suggested: `https://<ip>:8006` for a Proxmox VE host, otherwise `https://<ip>` and `ssh://<ip>`.
- An address typed without `https://` gets it added.
- Only `https`, `http`, `ssh` and `rdp` addresses get an **Open** button. Anything else is stored and can be copied, but is never a link.
- `ssh://` and `rdp://` links only do something when your computer has an app registered for them.

The address also shows in the credential list on wide screens, and the filter box and the search find a credential by it.

## One-time codes

Many admin logins ask for a six-digit code from an authenticator app. Store the secret behind that code with the credential and PrivateGlue shows the current code, so a shared login does not depend on one person's phone.

1. Edit the credential and paste the setup key into **One-time code secret**. That is the text a site shows next to its QR code, often under "can't scan the code?". A whole `otpauth://` link works as well.
2. **Test code** shows the code for what you pasted. Compare it with your authenticator app before you save.

The credential page then shows the code with a countdown. It refreshes by itself and turns amber in its last five seconds, when it is better to wait for the next one.

- The saved secret is never shown again. When editing, an empty field keeps it, a new value replaces it and **Remove the one-time code** deletes it.
- Anyone who can see the password can see the code.
- Only time-based codes work, the usual kind. The code is only right when the server's clock is right.

## Extra fields

For what does not fit a username and a password: an SSH private key, an API token, recovery codes. In the form, use the buttons under **Extra fields** to add one.

| Kind | For | On the credential page |
|---|---|---|
| Secret | One line, such as an API token | Hidden until you click the eye |
| Secret, several lines | Keys and recovery codes | Hidden; opens into a block you can scroll |
| Plain text | A tenant id or account number | Shown as is |

- Every value is encrypted like the password, the plain text kind too.
- Hidden values are not shown in the edit form. Leave the value empty to keep it. To delete a field, use its remove button and save.
- A credential can have 20 extra fields. A name can be 80 characters and a value 16,000.

Use these in place of the notes box for anything secret: the notes are stored as plain text.

## Password age and reminders

The credential page shows when the password was last changed.

- **Remind me to change it** in the form asks for a reminder after 90 days, 180 days or a year. A password that is due gets a **Due for renewal** badge on its page, a **Renew** badge in the list and a place in **Passwords to renew** on the dashboard. Type `renew` in the filter box to see only those.
- After a change, the **previous five passwords** stay on the credential page, encrypted, with the same show and copy buttons. That helps when a change never reached the device.
- Saving the same password again does not reset its age.
- Credentials from before this existed say **Age unknown** and are not flagged until their password is changed once.

## Tags

Give credentials tags the same way as notes: comma separated in the form, with buttons for tags you already use. Click a tag, on a credential or in the list, to see every credential that has it. The filter box matches tag names too.

Tags are saved in lower case. A credential can have 10 of them. Credential tags and note tags are separate lists.

## How passwords are protected

- Passwords, one-time code secrets, extra fields and previous passwords are encrypted before they are stored. The key is kept apart from the database, in the `secretkey` Docker volume.
- Without that key they cannot be read, by anyone. This is why the key must be part of your backups. See [Backup and restore](Backup-and-restore).
- A backup zip made in the app contains both the database and the key.

## Who can see them

Every account, including read-only, can read every stored password, code and extra field. See [Users and roles](Users-and-roles).

PrivateGlue records who opened a credential and who showed or copied a password. Administrators see that under [Activity](Activity-log) and at the bottom of each credential.

## What it is not

PrivateGlue documents the credentials of your infrastructure next to the devices they belong to. It is not a personal password manager: it has no browser extension, no auto-fill and no sharing with people outside.
