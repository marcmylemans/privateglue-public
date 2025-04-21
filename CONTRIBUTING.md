# Contributing to PrivateGlue

Thank you for considering contributing to PrivateGlue!  
Whether you’re reporting bugs, suggesting features, improving the documentation, or submitting code — your help is appreciated.

## 🛠 Ways to Contribute

- **Bug Reports** – Found something that’s not working? [Open an issue](https://github.com/marcmylemans/privateglue-public/issues).
- **Feature Requests** – Have an idea for improvement? Share it via a new issue with the `enhancement` label.
- **Documentation** – Fix typos, improve explanations, or clarify usage in the `README.md` or `CHANGELOG.md`.
- **Code Contributions** – Fork the repo, create a feature branch, and open a pull request when you're ready.
- **UI Feedback** – Screenshots, layout suggestions, and polish ideas are welcome.

## ⚙️ Development Setup

```bash
git clone https://github.com/marcmylemans/privateglue-public.git
cd PrivateGlue
docker-compose up --build
```

The app runs at: `http://localhost:5000`

## 🧪 Testing Your Changes

Ensure your changes don’t break anything:
- Test UI functionality in both light and dark mode
- If editing core modules (like `credentials`, `notes`, or `devices`), try creating/editing entries
- Use the `dev` or `test` branch if instructed

## 🚀 Guidelines

- Keep pull requests small and focused.
- Write clear commit messages.
- Follow existing code formatting (Python 3.11 / Flask / Bootstrap 5).
- Always use `flash()` for user feedback, and consistent UI button styles.

## 🔐 Security

If you discover a security vulnerability, **please do not open a public issue.**  
Instead, email [info@mylemans.online] to report it responsibly.

## 🙌 Thank You

Your contributions help make PrivateGlue better for home labbers, freelancers, and small teams everywhere. We’re glad you’re here.
