# Changelog

All notable changes to **PrivateGlue** will be documented in this file.

---


## [0.6.6-beta] - 2025-04-25

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
