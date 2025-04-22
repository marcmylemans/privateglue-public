# PrivateGlue

**PrivateGlue** is a simple, self-hosted web app for linking devices, notes, and credentials, helping IT professionals and homelabbers keep everything organized and secure.

Ideal for:
- Freelancers and consultants juggling multiple client systems
- Home lab enthusiasts documenting hardware and configurations
- Small businesses needing internal IT asset tracking
- Anyone looking to store credentials privately with encryption

---

## Features

- **Notes with Markdown** and device linking
- **Password manager** with encryption and copy-to-clipboard
- **Device inventory** with tags for location and type
- **Link notes and credentials to devices**
- **Dark Mode Support**
- Built with Flask, SQLite, Bootstrap 5

---

## Screenshots

### Dashboard Overview
![Dashboard Overview](https://mylemans.online/assets/img/privateglue/dashboard.png)

### Device View
![Device View](https://mylemans.online/assets/img/privateglue/device.png)

### Create a Note
![Create Note](https://mylemans.online/assets/img/privateglue/note.png)

### Add Credential
![Add Credential](https://mylemans.online/assets/img/privateglue/credential.png)

> _Screenshots taken from version 0.6.2_

---

## Getting Started

1. Clone this repository.
2. Run using Docker:

```bash
git clone https://github.com/marcmylemans/privateglue-public.git
cd privateglue-public
docker-compose up
```

3. Open `http://localhost:5000` and start documenting your gear!

More setup details coming soon...

---

## Use Case Examples

- Save login credentials per server/router/switch
- Track device locations and types (lab, office, rack)
- Write notes about setup instructions or recovery steps
- Share selected notes as public read-only docs (coming soon!)
- Backup your documentation easily (planned for future)

---

## Changelog
 
For a complete list of changes and versions, check out the [CHANGELOG.md](.source/documentation/CHANGELOG.md).

---

## ❤️ Support

If you like this project, consider [starring ⭐ it on GitHub](https://github.com/marcmylemans/privateglue-public)  
For feedback, suggestions, or bug reports, feel free to open an issue.

---

## 📜 License

MIT — free for personal and commercial use.
