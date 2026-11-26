# Activity

PrivateGlue records who did what, so you can answer "who looked at that password?" afterwards. Administrators find it under **Administration > Activity**.

## What is recorded

- Opening a credential, and showing or copying its password, one-time code, extra fields or previous passwords.
- Every change and delete of a credential, device or note.
- Uploading, downloading and deleting attachments.
- Sign-ins, failed sign-ins and sign-outs, and everything around two-factor sign-in.
- Changes to accounts, backups, integrations and settings.

Each entry has the time, the account, what happened, the item and the IP address it came from.

**Passwords, codes and keys are never written to the log.** It says that a password was changed, not what it was.

## Reading it

- **Filters**: a text box, a person, a kind of activity and a period.
- **Per credential**: administrators see the last ten entries at the bottom of each credential, with **View all** for its whole history.
- **Export CSV** downloads what the filters show, at most 50,000 rows. Times in the file are in UTC.

## Good to know

- Opening a credential counts as seeing its password, because the password is part of that page.
- The same person doing the same thing to the same item within a minute counts once. Failed sign-ins always count one by one.
- Entries are kept for 12 months and cannot be changed in the app.
- Entries stay when an account or an item is deleted.
- A failed sign-in stores the username that was typed. Someone who types their password into the username box by mistake leaves it in the log, where administrators can read it. If that happens, change that password.
- Behind a reverse proxy, the IP address is only the visitor's own when `TRUSTED_PROXIES` is set. See [Reverse proxy and HTTPS](Reverse-proxy-and-HTTPS).
- The log lives in the database, so it is part of every backup.
