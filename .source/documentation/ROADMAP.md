# 🗺️ PrivateGlue Project Roadmap

---

## ✅ Completed Sprints

### v0.6.7-beta
- Proxmox Auto-Fetch
- Import Devices Wizard 
- UI Refinements
- Data Handling Fixes

### v0.6.8-beta
- Secure network device discovery workflow (CSV import, header mapping, encoding fallback)
- Search bar enabled with `/search` route
- Standalone network probe (Python/Windows exe) for device discovery ([PrivateGlue-Probe](https://github.com/marcmylemans/PrivateGlue-Probe))
- Backend API `/api/discovered-devices` for probe results, secured with API key
- UI for reviewing/importing discovered devices (checkboxes, select all, selective import)
- System info page improvements: API key display (with copy button), version from container tag or git
- Automated API key generation and persistent storage for probe API
- Documentation for probe usage, security, and build in PrivateGlue-Probe/README.md

### **v0.6.0 – v0.6.2**
- Core functionality for Devices, Notes, and Credentials
- Linked devices and tags in markdown notes
- Role-Based Access Control (RBAC): admin, editor, readonly
- Live username availability and password strength check
- GitHub-inspired dark/light theme toggle

### **v0.6.3**
- Backup system (app.db, secret.key, markdown notes + meta.json)
- Restore option on first run (auto-detected or manual upload)
- Feedback messages and safe file handling

### **v0.6.4**
- Sessions expire unless “Remember Me” is selected
- Centralized RBAC and refined route protection
- First-run setup, login, and register UI polish

### **v0.6.5**
- Complete UI overhaul using GitHub dark theme as reference
- Consistent styling for Devices, Notes, and Credentials
- Live markdown preview for note editing
- Improved dashboard with recent entries for all modules

---

## 🚧 Sprint 6: **v0.6.6 – Web UI Enhancements**

**In Progress**
- Add site-wide footer
- Create admin-only "About / System Info" page
- Enable user profile page:
  - Change password
  - Delete own account (GDPR)
- Admin User Management:
  - Add/remove users
  - Assign or modify user roles
  - Force password reset on next login

**Stretch Goals**
- Add system overview on dashboard (e.g. version, uptime, db path)
- Add tooltips or popovers for inline guidance

---

## 🔮 Future Features (Planned for Later Sprints)

- Public notes (optional guest visibility)
- Role-based button visibility in templates (conditional rendering)
- MAC address detection from IP
- Hypervisor checkbox with type selector (VMware, Proxmox, Hyper-V)
- VM auto-scan if credentials exist (e.g. pull from hypervisor API)
- Device metadata improvements:
  - Serial number, manufacturer, model
  - Smart dropdown + manual input for type/location
- Enhanced tag management (list, edit, delete)
- Notification integration or automated backup scheduler

---

## 📝 Notes

We’re currently in a **feature freeze** on new modules until the UI/UX is fully optimized.  
Core functions are stable and ready for testing and community feedback.
