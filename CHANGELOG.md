# Changelog

All notable changes to **PrivateGlue** will be documented in this file.

# Changelog

## [0.6.2] - 2025-04-20

### Added
- Dashboard tile for "Credentials" with total count and quick access buttons
- "Recently Linked Credentials" section showing up to 5 most recent entries
- Flash messages for "Password copied to clipboard"
- Fallback-based Fernet encryption key generation if no `secret.key` is found
- Improved clipboard and password reveal features for credentials

### Changed
- Polished credentials index page layout and aligned it with other modules
- Refactored credential filtering dropdown and routing logic
- Restored filter functionality on device index page using session-based filters
- Standardized UI spacing for dashboard cards and button alignment

### Fixed
- Password decryption issues due to invalid encoding
- Title not being prefilled when adding credentials from device view
- Broken `Clear Filters` link in credential view due to missing route
- Minor inconsistencies in filter dropdowns

---

## [v0.6.1] - 2025-04-20

### Added
- 🔐 **Password Manager Module**: Create, edit, view, and delete credentials.
- 🖇 **Linking Credentials to Devices**: Credentials can now be associated with multiple devices.
- 👁 **Password Show/Hide Toggle** and **Copy to Clipboard** functionality.
- ⚙️ **Password Generator**: Configurable password generator with options for length, symbols, and digits.
- 🔐 **Fernet Encryption**: Passwords are now encrypted at rest using symmetric key encryption.
- 📁 **Automatic Key Generation**: `secret.key` is created automatically and stored using a Docker volume (`/app/data/secret.key`).
- 🌙 **Improved Dark Mode Support**: Better contrast for inputs, badges, and flash messages.
- 📎 Device name auto-prefills when adding a credential from a device.
- 💬 Copy actions now show non-intrusive flash messages instead of popups.

### Fixed
- 🐛 Credential title now properly pre-fills when accessed from device context.
- 🔒 Fixed encryption errors caused by invalid Fernet padding or duplicate encoding.
- 🛠 Credential model properly handles both strings and encrypted bytes.

### Changed
- ♻️ Refactored encryption logic to handle missing keys, invalid tokens, and graceful fallback.
- ✨ UI tweaks across credential forms and device views.

---

## [v0.6.0] - 2025-04-20

### Added
- 📂 **Credential Manager**: New feature to manage credentials (passwords, usernames, notes) with:
  - Secure storage in the database
  - Linked devices (multi-select support)
  - Password visibility toggle and clipboard copy
  - Built-in password generator with configurable length and characters
- 🌐 Navigation bar: Added direct link to credentials for easy access

### Improved
- Device view now shows linked credentials alongside notes
- When creating a credential via `?device_id=...`, the form pre-fills title and links automatically
- Flash messages used for clipboard feedback instead of blocking popups
- Form field validations and better default behavior

### Fixed
- Database field mismatch in Credential model (`name` → `title`)
- Error on device view when credentials lacked expected fields
- Repetitive keyword arguments in route rendering
- Filtering and visibility issues in dark mode

### Changed
- Refactored credentials view routes to include individual view pages
- Consistent use of `flash()` for user feedback
- Cleaned up form submission error handling

---

## [v0.5.0] - 2025-04-19

### ✨ Added
- Linked Notes to Devices with full roundtrip (view, edit, create)
- Split-pane markdown editor with live preview on note edit
- Device view page now shows notes it's linked to
- Note filtering supports tags and linked devices (saved in session)
- Light/Dark mode toggle with auto-detect and localStorage
- User authentication and login/logout interface
- "Clone Device" functionality to duplicate hardware entries

### 💄 Improved
- Full Bootstrap 5 styling overhaul
- Improved flash message visibility
- Updated layout and navigation (dropdowns, themes, session UI)
- Markdown content styled using GitHub markdown CSS
- Custom `custom.css` added for better dark mode compatibility

### 🐛 Fixed
- Persistent database volume via Docker Compose
- Dark mode text visibility issues (light on light / dark on dark)
- URL generation bugs for clone/edit routes
- Metadata `.md.md` filename duplication issue

---

## [v0.3.0] - 2025-04-19

### Added
- 🔎 Global search for devices and notes from the top navbar
- 🧭 Navigation bar with improved styling and page structure
- 📝 Notes now support **multiple linked devices** via `device_ids`
- 🏷️ Tag filtering for notes, with badge UI
- 🖥️ Filter UI for Devices:
  - Filter by type and location
  - Clickable filter badges
  - Filters persist via session
- 📎 Notes now show all linked devices (with badges)
- 🧠 Clone device functionality (prefills form with existing data)
- 📁 Clean and styled note viewer (Markdown display + badges)

### Changed
- 🛠 Notes metadata structure from `device_id` → `device_ids` for multi-device support
- 💄 Updated `form.html` for device add/edit/clone logic
- 🎨 UI improvements in `view.html` and `index.html` for consistency

### Fixed
- ❌ Clear filter not working when badge links were clicked (now handled properly)
- 🛠 Broken route references (`notes_by_tag`) in templates replaced with working query params

---

