# Users and roles

## The first account

The account created on the setup screen is the administrator. After that there is no public sign-up: an administrator adds everyone else.

## Roles

| | Read-only | Editor | Administrator |
|---|---|---|---|
| See devices, notes and credentials | yes | yes | yes |
| **Read stored passwords** | yes | yes | yes |
| Add and change devices, notes and credentials | | yes | yes |
| Import devices (CSV, discovered devices) | | yes | yes |
| Upload attachments | | yes | yes |
| Delete devices, notes, credentials and attachments | | | yes |
| See the activity log | | | yes |
| Manage accounts | | | yes |
| Backups, integrations, probe key, scanning from the server | | | yes |

**Every role can read stored passwords.** A read-only account is for someone who may see everything but should not change it. It is not a way to hide passwords.

## Add someone

1. Open **Users** and click **Add user**.
2. Choose a username, a temporary password and a role.
3. Give the person the temporary password. They must choose their own at first sign-in.

## Change or remove someone

Under **Users** you can change a role, set a new password or delete an account.

- Changing someone's role or password signs them out everywhere at once.
- The last administrator cannot be removed or demoted. Make someone else an administrator first.

## Your own account

Open the menu with your name at the top right and choose **Profile & password** to change your password. Changing it signs out your other devices.

The same page is where you turn on [two-factor sign-in](Two-factor-sign-in).

## Forgotten password

Another administrator can set a new one under **Users**. If the only administrator is locked out, restore your latest backup into a fresh install and sign in with a password you know from that time. There is no password reset by e-mail.
