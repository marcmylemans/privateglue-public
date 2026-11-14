# GitHub notes sync

Keeps your PrivateGlue notes as markdown files in a GitHub repository. Use it in one of two
ways:

- **Push** (default): PrivateGlue is where you write. Every sync commits the notes that
  changed to GitHub, so you get an off-site copy with full history.
- **Pull**: GitHub is where you write (in the web editor, VS Code, Obsidian with a git
  plugin, anything). Every sync copies new and changed notes into PrivateGlue.

It works with github.com and with GitHub Enterprise Server.

**One direction per sync, no two-way merge.** If you edit the same note in PrivateGlue and on
GitHub, the direction you picked wins the next time that note changes on the winning side.
Pick the side you edit on and stick to it.

**Nothing is ever deleted**, on either side. A note you delete in PrivateGlue stays in the
repository (and in its history); a file you delete on GitHub stays in PrivateGlue. Delete it
on the other side by hand if you want it gone.

## Create the access token

Use a fine-grained personal access token that can only reach this one repository.

1. Create the repository on GitHub first (private is recommended). For push, tick
   **Add a README file** so the repository has a first commit and a branch: the sync cannot
   commit to a completely empty repository.
2. On GitHub, open your profile picture > **Settings** > **Developer settings** >
   **Personal access tokens** > **Fine-grained tokens** > **Generate new token**.
3. Give it a name such as `privateglue-notes` and an expiration date. Put a reminder in your
   calendar: when the token expires, syncs fail with "rejected the access token (HTTP 401)".
4. **Resource owner**: you, or the organization that owns the repository (an organization
   may have to approve the token first).
5. **Repository access**: **Only select repositories**, and pick the one notes repository.
6. **Permissions** > **Repository permissions** > **Contents**:
   - **Read and write** for push.
   - **Read-only** is enough for pull.

   GitHub adds **Metadata: Read-only** by itself. Nothing else is needed.
7. Generate the token, copy it and paste it into the **Access token** field in PrivateGlue.
   It is stored encrypted and never shown again.

A classic token with the `repo` scope also works, but it can reach every repository you
have access to. Use the fine-grained one.

## Settings

| Setting | What it does |
|---|---|
| Repository | `owner/name`, for example `acme/it-notes`. A pasted GitHub URL is accepted too. |
| Branch | The branch to read from and commit to. Default `main`. It must already exist. |
| Folder in the repository | Where the notes live in the repository. Default `notes`. Leave empty for the top of the repository. For push the folder is created by the first commit. |
| Access token | The fine-grained token from above. Leave empty when saving to keep the stored one. |
| Direction | **Push: PrivateGlue to GitHub** (default) or **Pull: GitHub to PrivateGlue**. |
| Include tags and device links | On by default. Also syncs the tags and linked devices of each note (see below). |
| API address | `https://api.github.com` for github.com. For GitHub Enterprise Server use `https://<your-server>/api/v3`. |
| Verify the TLS certificate | On by default. Turn off only for a GitHub Enterprise Server with a self-signed certificate. |

**Test connection** checks that the repository and branch are reachable and, for push, that
your GitHub account has write access to the repository. GitHub reports the access of your
account, which is not always the same as what the token allows, so a token with only read
access can still pass the test: the first push then stops with "refused access (HTTP 403)".
Test connection never writes anything.

## What is synced

- **Notes**: every `.md` file at the top level of PrivateGlue's notes folder, as the same
  file name in the repository folder.
- **Tags and device links**: PrivateGlue keeps them in a small file next to each note,
  `<note>.md.meta.json`, for example:

  ```json
  {
    "tags": ["network", "core"],
    "device_ids": [3, 12]
  }
  ```

  With "Include tags and device links" on, that file is synced exactly like the note. One
  small file per note was chosen over one shared index file because it is how PrivateGlue
  already stores it, a change to one note touches only that note's files, and two edits never
  fight over a shared file.

  `device_ids` are PrivateGlue's internal device numbers. They only mean something in the
  PrivateGlue install they came from. Pulling into a different install links notes to
  whichever devices have those numbers there, so turn the option off in that case.

### Push

- Changed notes go into **one commit per sync**, with a message such as
  `PrivateGlue notes sync: 3 changed`. When nothing changed, no commit is made.
- Unchanged notes cost nothing: PrivateGlue computes the same fingerprint git uses (the
  blob sha) and compares it with what GitHub lists, so it only sends what differs.
- Files in the repository folder that PrivateGlue does not have are left alone, as is
  everything outside the folder.
- If somebody pushed to the branch during the sync, nothing is written and the sync asks you
  to run it again.

### Pull

- Only `.md` files at the top level of the repository folder are imported, with their
  `.md.meta.json` file when the option is on. Subfolders are ignored: PrivateGlue notes are
  one flat list, and folder names would not survive the file name rules below.
- A file is only downloaded when it differs from the local copy.
- New files are created, changed files are overwritten, local notes that are not in the
  repository are kept.
- With the folder setting empty, files such as the repository's `README.md` become notes too.
  Keep the notes in their own folder to avoid that.
- Tags and device links from the repository are cleaned up the same way the note editor does
  (empty tags dropped, device ids must be numbers).

## What is skipped

A skipped file does not stop the sync. It shows up as a line in the run history.

- File names PrivateGlue would not accept itself: only letters, numbers, dashes,
  underscores and dots, ending in `.md`. Spaces and accented letters are not allowed (the
  note editor turns `My note` into `My_note.md`). Rename the file on GitHub and sync again.
- Files larger than 1 MB.
- Files that are not UTF-8 text.
- Symlinks and submodules in the repository, and local files that point outside the notes
  folder.

## When it fails

| Message | What to do |
|---|---|
| rejected the access token (HTTP 401) | The token is wrong, expired or revoked. Create a new one. |
| refused access (HTTP 403) | The token does not have this repository or lacks Contents permission (read and write for push). |
| answered 404 | The repository name is wrong, or the token was not given access to it. |
| Branch 'x' does not exist | Create the branch on GitHub or fix the setting. |
| the repository is empty | Add a first file on GitHub (a README) so there is a branch. |
| rate limit reached | GitHub limits how many requests a token makes. The message says when to try again. The sync does not retry by itself. |

## Limits

- One direction per sync, no merge, no deletes (see above).
- Notes only. Devices and credentials are never sent to GitHub.
- The commit author is the GitHub account that owns the token.
- A folder with more than 100,000 entries is not fully listed by GitHub; the run history then
  shows a warning.
