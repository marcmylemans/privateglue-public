# Changelog

All notable changes to **PrivateGlue** will be documented in this file.

---

## Unreleased

## v0.8.2 (2026-11-25)

### Fixed
- **UniFi: a filled-in username and password are now used.** In v0.8.1 they were ignored while
  "Sign in with" still said "API key", and the test answered "Fill in the API key". The settings
  page now also shows only the fields of the way you chose.

## v0.8.1 (2026-11-25)

### Added
- **UniFi: sign in with username and password.** The self-hosted UniFi Network Server cannot
  create API keys, so the integration could not be used with it. Choose "Username and password"
  under "Sign in with" and use a local, view-only account. Signing in with an API key keeps
  working as before.

## v0.8.0 (2026-11-24)

### Added
- Versions now follow one scheme, `vBIG.SMALL.FIX` (for example `v0.8.0`), so every release
  also gets its own Docker image tag. The four-part versions `v0.7.0.1` to `v0.7.0.3` were
  the last of their kind.
- **More names in a scan from the server.** Besides DNS, the scan now asks each device for
  its NetBIOS name (Windows, NAS, Samba) and its mDNS name (Apple, Linux, printers). Devices
  that showed as a bare IP address now often show with their name.
- The server itself now shows with its MAC address in the scan result.

## v0.7.0.3 (2026-11-24)

### Changed
- **Scanning from the server is now a switch in the app.** An administrator turns it on under
  Devices > Discovered, without editing `.env` or restarting. It is still off by default.
  `ALLOW_SERVER_SCAN=true` keeps working and keeps it on. New: `ALLOW_SERVER_SCAN=never`
  keeps it off and hides the switch, for a server you share with others.

### Changed
- The user guide is now also published at https://privateglue.app/docs, with search. It is
  built from the same pages as the wiki and follows every release.

## v0.7.0.2 (2026-11-14)

### Fixed
- **Restoring a backup now takes effect by itself.** The app reloads after a restore, so the
  restored accounts and stored passwords work straight away. Before, the old database and
  encryption key stayed in use until someone restarted the container, and the notice that
  asked for it was easy to miss. A "Backup restored" page shows while it reloads.

### Removed
- The unused `/admin/restore` address. It could replace the database of a running install
  with a backup file from the backups folder. Restoring is only offered on the setup screen
  of a new install.

## v0.7.0.1 (2026-11-14)

### Added
- **Install on Proxmox VE without Docker.** One command in the Proxmox shell creates an LXC
  container and installs PrivateGlue in it as a systemd service, built on the community-scripts
  engine. `update` inside the container moves to the newest release and keeps your data. See
  "Install on Proxmox VE" in the guide.
- `PRIVATEGLUE_HOME`: the folder that holds data, notes, backups and the encryption key, for
  installs without Docker. The default is `/app`, so Docker installs do not change.
- Every release now comes with `privateglue-<version>.tar.gz` on the public repo: the app
  without Docker files or tests, which is what the Proxmox script downloads.

### Security
- **Sign-up is closed after the first account.** `/register` only works on a new install to
  create the first admin. Before, anyone who could reach the login page could create a
  read-only account, and read-only accounts can read every stored password. Admins create
  accounts under Users.
- Changing a password (or an admin changing a user's role or password) signs out every other
  session of that user.
- "Must change password at next sign-in" is now enforced: the user can reach nothing else first.
- The last administrator can no longer delete their own account (that would reopen the setup
  wizard for the next visitor).
- Signing out and creating a backup need a button press (POST). A link or an image in a note
  can no longer trigger them.
- Pages send a Content-Security-Policy: only the app's own scripts run. External images in
  notes still load over https; plain http images no longer do.
- Pages are no longer stored in browser or proxy caches.
- Redirects after sign-in and after a "no permission" message only go to pages of this app.
- The username check no longer answers anonymous visitors.
- Extra login rate limit per username (20 attempts an hour), next to the existing limit per address.
- New `TRUSTED_PROXIES` setting so rate limits see real visitor addresses behind a reverse proxy.
- Probe results are reduced to the known device fields before they are kept.
- Proxmox fetch errors no longer show internal details on the page.

- Updated Flask, Markdown, bleach, cryptography and requests to versions without known
  vulnerabilities (21 known issues in the old versions).

### Added
- **A user guide.** Installing, configuration, updating, backup and restore, reverse proxy,
  users, devices, network scan, integrations, notes, credentials, security and
  troubleshooting. It is written in `documentation/wiki` and published to the wiki of
  privateglue-public on every release.
- **Scan from this server.** Administrators can scan a private network straight from
  PrivateGlue under Devices > Discovered, without the separate probe. The result lands in
  the same review list. It is off unless you set `ALLOW_SERVER_SCAN=true`, only accepts
  private ranges and at most 1024 addresses per scan, and can also find machines that do
  not answer ping by trying a few common ports.
- **`docker-compose.host.yml`**: runs PrivateGlue on the host network. The scan needs that
  to see MAC addresses. It uses the same folders and key volume, so you can switch an
  existing install by swapping the compose file.
- The image now contains `ping` and `ip` for the scan.

### Changed
- **Every way to add devices is now in plain sight.** The device list has an Import menu
  (CSV file, network probe, sync from another system), the Add device page shows the same
  options next to the form, and so do the empty device list and the dashboard's New menu.
- The Discovered devices page always explains the probe in three steps, with a download
  link, the address and (for administrators) the key. Before, it was an empty page until a
  probe had already run.
- Device list: click a column header to sort. Administrators can tick several devices and
  delete them in one go, which helps after an import brought in too much.
- A device that came from an integration shows "Synced from" with a link to its record in
  the other system.
- Integrations: each one has a setup guide that opens inside the app, and Test connection
  and Sync now sit next to the settings instead of below them, with the current state.
- The device page's "Integrations" panel (live Proxmox and SNMP details) is now called
  "Live details", so it is not confused with the Integrations page.
- System page: the probe key row points to where the key is managed.

### Fixed
- Network probe: discovered devices no longer come and go between page loads. The list was
  kept in memory by whichever worker received it; it is now stored in the data folder and
  shared by all workers, and survives a restart.
- Network probe: importing can no longer pick the wrong devices when the probe sends a new
  list while the review page is open.

### Changed
- Existing installs: one column is added to the user table automatically on start. Everyone
  stays signed in.

### Added
- Network probe set-up for administrators under Devices > Discovered: the address, the API
  key (hidden until shown, with a copy button) and a button to create a new key. Before, the
  key could only be read from a file in the data volume.
- "Clear list" on the discovered devices page, and the time the list was received.
- The probe API answers with a readable JSON error and only keeps entries with a valid IP address.
- Integrations (Administration > Integrations, admins only): a common home for modules that
  connect PrivateGlue to other systems. Per integration: settings, test connection, sync now,
  an optional automatic schedule and a run history. Tokens are stored encrypted. Everything
  is off until you turn it on. See `documentation/integrations/README.md`.
- First five integrations, all off until you turn them on. Each has its own page under
  `documentation/integrations/`:
  - **NetBox**: imports devices and, optionally, virtual machines from NetBox 3.7 to 4.x
    (read-only, v1 and v2 tokens, status, site and tag filters).
  - **Proxmox VE**: imports cluster nodes, virtual machines and containers with a read-only
    API token.
  - **UniFi Network**: imports UniFi gateways, switches and access points, and optionally
    connected clients, using an API key.
  - **Microsoft Intune**: imports managed devices (name, serial, MAC, OS, version, type)
    through Microsoft Graph with a read-only app registration.
  - **GitHub notes sync**: pushes your notes to a GitHub repository as backup and history,
    or pulls them from one. One direction per run, nothing is ever deleted.
- `INTEGRATIONS_SCHEDULER=off` turns off automatic syncs.

---

## [0.6.8-BETA2] - 2025-05-20

### Added
- Automatic database upgrade logic for SQLite:
  - Adds missing columns (like `mac_address`) on container startup.
  - Ensures compatibility with SQLAlchemy model changes without manual migration.
- Improved startup flow in `app.py` to run `check_and_upgrade_database()` before `db.create_all()`.

### Fixed
- Startup crash due to missing `mac_address` column in `Device` model after upgrading container.

### Notes
- This is a temporary solution for SQLite users until full Alembic integration.
- Future schema changes should transition to Alembic migrations for production readiness.


---

## v0.6.8-beta – 2025-05-19

### Added

- Network Device Discovery Workflow:
    - CSV import with header mapping and encoding fallback
    - Search bar enabled with `/search` route
    - Standalone network probe (Python/Windows exe) for device discovery ([PrivateGlue-Probe](https://github.com/marcmylemans/PrivateGlue-Probe))
    - Backend API `/api/discovered-devices` for probe results, secured with API key
    - UI for reviewing/importing discovered devices (checkboxes, select all, selective import)
    - System info page improvements: API key display (with copy button), version from container tag or git
    - Documentation for probe usage, security, and build in PrivateGlue-Probe/README.md

### Changed

- Automated API key generation and persistent storage for probe API
- System info page now prefers container version (`APP_VERSION` env) over git tag

### Fixed

- Robust CSV import field mapping and error handling
- UI/UX for device import and discovered devices review

---

## [0.6.8-beta] – 2025-05-19

### Added

- Network Device Discovery Workflow:
  - CSV import with header mapping and encoding fallback
  - Search bar enabled with `/search` route
  - Standalone network probe (Python/Windows exe) for device discovery (see [PrivateGlue-Probe](https://github.com/marcmylemans/PrivateGlue-Probe))
  - Backend API `/api/discovered-devices` for probe results, secured with API key
  - UI for reviewing/importing discovered devices (checkboxes, select all, selective import)
  - System info page improvements: API key display (with copy button), version from container tag or git
- Documentation for probe usage, security, and build in PrivateGlue-Probe/README.md

### Changed

- Automated API key generation and persistent storage for probe API
- System info page now prefers container version (`APP_VERSION` env) over git tag

### Fixed

- Robust CSV import field mapping and error handling
- UI/UX for device import and discovered devices review

---

## [0.6.7-beta] – 2025-04-28

### Added

- Experimental Proxmox Auto-Fetch:
  - Detect Proxmox VE by OS field and prompt to link credentials
  - Pull host summary (CPU, memory, uptime), VM and LXC stats, storage pools via Proxmox API
  - Human-friendly units (GiB, “3 d 4 h 15 m”, etc.) with graceful fallbacks
- Import Devices wizard:
  - “Import Devices” button on the devices list
  - Downloadable CSV template matching device model fields
  - CSV upload form to bulk-create devices

### Changed

- Moved “Delete” action off the device list into the edit/detail views
- Enhanced credential form to prefill title, username, and pre-select linked devices

### Fixed

- Robust byte-formatting guard to handle non-numeric or nested memory fields

### Removed

- Direct “Download CSV Template” button (now part of the import wizard)

---

## [0.6.6-beta2] - 2025-04-25

### Fixed

- Disable /profile access for demo user

---

## [0.6.6-beta] - 2025-04-25

### Added

- New **About / System Info** page (admin-only) with:
  - App version, mode (Demo/Production), and current time
  - Database engine and counts for users, devices, notes, credentials
- Icon added for About page in the navbar (admin dropdown)

### Fixed

- Visibility issue for linked notes on device detail pages
- Resolved several Flask `NameError` and `BuildError` exceptions
- Corrected `datetime` usage in the system info page

---

## [v0.6.5-demo] - 2025-04-24

### Added

- Demo mode support (`DEMO_MODE=True`) via environment variable:
  - Displays a persistent banner warning that the instance resets hourly.
  - Adds a custom footer with a "Powered by DigitalOcean" badge and GitHub project link.
  - Pre-fills demo login credentials on the login screen (read-only/editor access).
- Footer now shows in all views with clean styling in both light/dark modes.

### Changed

- Restructured footer layout to be visually cleaner and more aligned with GitHub’s aesthetic.
- Improved context processor to cleanly inject `DEMO_MODE` for all templates.

### Notes

- This version is intended for preview and testing purposes only.
- Do **not** use this version in production.

---

## [0.6.5] - 2025-04-23

### Added

- Custom 404 and 403 error pages with clean layout
- Placeholder view for `/search` ("Coming soon")

### Improved

- UI/UX overhaul across the app to match GitHub’s aesthetic
  - Updated layout and spacing in devices, credentials, and notes views
  - Redesigned dashboard card layout
  - First-run setup and registration pages made more user-friendly
- Dark mode markdown preview in note editor
- Registration form now includes:
  - Live username availability check
  - Color-coded password strength feedback

### Fixed

- Form layout and spacing consistency
- Flash messages and live previews working across light/dark themes

---

## [v0.6.4] - 2025-04-23

### Added

  - Role-Based Access Control (RBAC):
  - `admin_required`, `editor_required`, and `readonly_required` decorators.
  - Credential create/edit/delete requires editor rights.
  - Admin panel (backup/restore) restricted to admins only.

- Session Expiration Handling:
  - Sessions now expire unless "Remember Me" is checked during login.
  - Default expiration is set to 1 hour (`app.permanent_session_lifetime`).
  - Graceful fallback for non-persistent sessions on restart or logout.

### Changed

  - Centralized SQLAlchemy `db` import across route modules using:
  `from backend.models.devices import db`

### Removed / Postponed

  - Macro-based role button visibility was removed due to template context issues (`current_user` undefined).
  - Logged for future UI/UX sprint.

### Verified

- All core RBAC protections tested with all roles.
- Admin-only backup and restore functionality revalidated.
- Session logic functions correctly with or without persistent login.

---

## [0.6.3] - 2025-04-22

### 🚀 Added

- **Backup Feature (Admin only)**:
  - Creates a ZIP archive containing:
    - `app.db` database
    - `secret.key` Fernet encryption key
    - All `.md` notes and `.meta.json` file
  - Files stored under `/app/backups/` (bindable via Docker)
  - Flash message now includes a **direct download link** to the ZIP file.

- **Restore Feature during First Run**:
  - Detects if users are missing and a backup is available.
  - Allows automatic or manual upload and restore of ZIP backups.
  - UI prompts restoration or skips to registration.
  - Friendly error handling and validation.
  - Admin-only route also supports manual upload and restore.

- **Optional graceful shutdown** after backup restore to reinitialize encryption and DB state.
  - Works in local development mode using `os.execv` or `werkzeug` shutdown logic.

- **Admin Panel Placeholder**: Framework ready for future admin-only tools (e.g., audit logs, system info, etc.)

- **Documentation Directory**: Created `/documentation/` folder structure inside private repo to prepare for:
  - Markdown-based internal documentation
  - Dev logs, architecture plans, and technical write-ups
  - Central location for changelog and system planning

### 🔧 Changed

- Backup now includes `.meta.json` for note metadata
- Routes and templates cleaned up for first-run wizard
- Improved Docker Compose setup for:
  - Optional health checks
  - Proper volume mounts for `/app/backups`, `/app/data`, `/app/notes`, `/app/secret`
- Changelog relocated to `documentation/changelog.md`

### 🐛 Fixed

- FileNotFound errors when backup folder was missing
- Restore logic not detecting uploaded file on first run
- Skip button triggering unwanted file validation
- User experience flow issues in first-time setup
- Legacy SQLAlchemy warning on `User.query.get()` (now adjusted)

---

## [0.6.2] — 2025-04-20

### ✨ Added

- Dashboard tile for "Credentials" with total count and quick access buttons
- "Recently Linked Credentials" section showing up to 5 most recent entries
- Flash message for "Password copied to clipboard"
- Fernet key fallback generation if `secret.key` is missing
- Improved clipboard and password reveal behavior

### 💄 Changed

- Aligned credential index layout with device/note style
- Polished credential filtering dropdown and routing logic
- Restored session-based filtering on device index page
- Unified UI spacing and button alignment on dashboard

### 🐛 Fixed

- Password decryption failures due to invalid encoding
- Prefilled title missing when adding credentials from a device
- Missing route for "Clear Filters" in credentials view
- Misc. inconsistencies in filter dropdown display

---

## [0.6.1] — 2025-04-20

### ✨ Added

- **Password Manager Module**: Create, edit, and manage encrypted credentials
- **Multi-device Linking**: Credentials can be linked to multiple devices
- **Password Visibility & Clipboard Copy**: Toggle and copy password on view
- **Password Generator**: Customizable password generator
- **Fernet Encryption**: All passwords are encrypted at rest
- **Auto Key Generation**: Automatically creates and persists `secret.key` in Docker volume
- **Dark Mode Enhancements**: Improved badge and flash message readability
- **Device Context Support**: Auto-prefill title when adding credential from a device
- **Flash Feedback**: Copy-to-clipboard actions now use flash messages

### 💄 Changed

- Refactored encryption logic and error handling
- UI refinements across credential-related forms and views

### 🐛 Fixed

- Proper handling of encrypted password bytes
- Fixed Fernet-related errors (duplicate encoding, padding issues)
- Corrected credential title prefill logic

---

## [0.6.0] — 2025-04-20

### ✨ Added

- Credential Manager:
  - Secure storage with encryption
  - Multi-device linking
  - Visibility toggle and copy functionality
  - Built-in password generator
- Credentials in navigation bar
- Device view now shows linked credentials

### 💄 Changed

- Refactored credential routes to support view/edit/delete
- Improved flash message consistency
- Better error handling for invalid credentials

### 🐛 Fixed

- Incorrect field reference (`name` → `title`)
- Errors when credentials lacked linked device data
- Dark mode filter and contrast issues

---

## [0.5.0] — 2025-04-19

### ✨ Added

- Device–Note linking with full roundtrip
- Live Markdown preview in note editor
- Device view shows linked notes
- Session-based filtering for notes and devices
- Dark/light mode toggle with auto-detect
- Authentication system (login/logout UI)
- Device cloning functionality

### 💄 Changed

- Complete Bootstrap 5 UI overhaul
- Improved layout and navigation
- GitHub-style Markdown display
- Custom dark mode CSS

### 🐛 Fixed

- Persistent Docker volumes
- Visibility issues in dark mode
- Metadata filename cleanup (`.md.md`)
- Broken route references

---

## [0.3.0] — 2025-04-19

### ✨ Added

- Global search from navbar
- Enhanced navbar styling and navigation
- Multi-device support for notes
- Tag filtering with badge UI
- Device filter (type/location) with session persistence
- Linked devices displayed on notes
- Note viewer with full markdown styling

### 💄 Changed

- Notes metadata refactored for multi-device support
- Updated device form handling (add/edit/clone)
- Improved visual consistency across modules

### 🐛 Fixed

- Filter clearing now works reliably
- Template route references corrected
