"""How an action name reads in the activity log, and which kind of activity it belongs to."""

# Sentences for the admin page. Short, past tense, no subject ("Copied password").
SENTENCES = {
    "credential.viewed": "Opened credential",
    "credential.created": "Created credential",
    "credential.updated": "Changed credential",
    "credential.deleted": "Deleted credential",
    "credential.password_copied": "Copied password",
    "credential.password_shown": "Showed password",
    "credential.username_copied": "Copied username",
    "credential.address_opened": "Opened address",
    "credential.code_copied": "Copied one-time code",
    "credential.field_shown": "Showed extra field",
    "credential.field_copied": "Copied extra field",
    "credential.old_password_shown": "Showed old password",
    "credential.old_password_copied": "Copied old password",
    "device.created": "Added device",
    "device.updated": "Changed device",
    "device.deleted": "Deleted device",
    "note.created": "Created note",
    "note.updated": "Changed note",
    "note.deleted": "Deleted note",
    "attachment.uploaded": "Uploaded attachment",
    "attachment.downloaded": "Downloaded attachment",
    "attachment.deleted": "Deleted attachment",
    "auth.signed_in": "Signed in",
    "auth.sign_in_failed": "Sign-in failed",
    "auth.signed_out": "Signed out",
    "auth.password_changed": "Changed password",
    "auth.two_factor_enabled": "Turned on two-factor",
    "auth.two_factor_disabled": "Turned off two-factor",
    "auth.two_factor_reset": "Reset two-factor",
    "auth.two_factor_failed": "Two-factor code failed",
    "auth.recovery_code_used": "Used a recovery code",
    "user.created": "Added user",
    "user.updated": "Changed user",
    "user.deleted": "Deleted user",
    "user.password_reset": "Reset user password",
    "backup.created": "Created backup",
    "backup.downloaded": "Downloaded backup",
    "backup.restored": "Restored backup",
    "integration.settings_saved": "Changed integration settings",
    "integration.sync_started": "Started a sync",
    "settings.server_scan_changed": "Changed server scan setting",
    "settings.probe_key_replaced": "Replaced probe key",
    "settings.two_factor_policy_changed": "Changed two-factor policy",
    "audit.exported": "Exported activity",
}

# The same, as the end of "<user> ..." in the Activity panel of a credential.
PANEL_PHRASES = {
    "credential.viewed": "opened this credential",
    "credential.created": "created this credential",
    "credential.updated": "changed this credential",
    "credential.password_copied": "copied the password",
    "credential.password_shown": "showed the password",
    "credential.username_copied": "copied the username",
    "credential.address_opened": "opened the address",
    "credential.code_copied": "copied the one-time code",
    "credential.field_shown": "showed an extra field",
    "credential.field_copied": "copied an extra field",
    "credential.old_password_shown": "showed an old password",
    "credential.old_password_copied": "copied an old password",
    "attachment.uploaded": "uploaded an attachment",
    "attachment.downloaded": "downloaded an attachment",
    "attachment.deleted": "deleted an attachment",
}

# What the browser may report. Everything else is refused.
BROWSER_ACTIONS = frozenset({
    "credential.password_copied",
    "credential.password_shown",
    "credential.username_copied",
    "credential.address_opened",
    "credential.code_copied",
    "credential.field_shown",
    "credential.field_copied",
    "credential.old_password_shown",
    "credential.old_password_copied",
})

# Kinds for the filter: value -> (label, action prefixes).
KINDS = {
    "credentials": ("Credentials", ("credential.",)),
    "devices": ("Devices", ("device.",)),
    "notes": ("Notes", ("note.",)),
    "attachments": ("Attachments", ("attachment.",)),
    "signins": ("Sign-ins", ("auth.",)),
    "users": ("Users", ("user.",)),
    "backups": ("Backups", ("backup.",)),
    "settings": ("Settings", ("settings.", "integration.", "audit.")),
}

_SECRET_EXACT = {"credential.address_opened", "attachment.downloaded", "backup.downloaded",
                 "audit.exported", "auth.recovery_code_used"}
_PLAIN_EXACT = {"auth.signed_out", "integration.sync_started", "backup.created"}


def sentence(action):
    """'credential.password_copied' -> 'Copied password'; unknown names read tidily."""
    if action in SENTENCES:
        return SENTENCES[action]
    thing, _, what = (action or "").partition(".")
    thing = thing.replace("_", " ").strip()
    what = what.replace("_", " ").strip()
    if not what:
        return thing.capitalize() or "Something happened"
    return f"{thing.capitalize()}: {what}" if thing else what.capitalize()


def panel_phrase(action):
    if action in PANEL_PHRASES:
        return PANEL_PHRASES[action]
    text = sentence(action)
    return text[:1].lower() + text[1:]


def tone(action):
    """A colour family for the action chip: danger, secret, good, change or plain."""
    action = action or ""
    if action.endswith(("_failed", ".deleted", "two_factor_disabled")):
        return "danger"
    if action.endswith(("_copied", "_shown")) or action in _SECRET_EXACT:
        return "secret"
    if action == "auth.signed_in":
        return "good"
    if action.endswith(".viewed") or action in _PLAIN_EXACT or action not in SENTENCES:
        return "plain"
    return "change"
