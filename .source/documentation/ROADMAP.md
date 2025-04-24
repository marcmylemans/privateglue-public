# 🗺️ PrivateGlue Project Roadmap

---

## ✅ Completed Sprints

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
