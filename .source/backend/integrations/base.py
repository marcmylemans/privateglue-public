"""Base classes every integration module builds on."""
from dataclasses import dataclass, field as dc_field


class IntegrationError(Exception):
    """Raise with a message an admin can act on ("Token rejected by NetBox (403)")."""


@dataclass
class Field:
    """One setting on the integration's settings page.

    kind: text, url, password, number, checkbox, select or textarea.
    show_if: (other field, value) to show this field only for that choice of a select.
    secret: stored encrypted and never sent back to the browser. Use it for tokens and
            passwords. kind="password" implies secret.
    """
    name: str
    label: str
    kind: str = "text"
    required: bool = False
    secret: bool = False
    default: object = None
    help: str = ""
    placeholder: str = ""
    choices: list = dc_field(default_factory=list)  # for select: [(value, label), ...]
    # Only show this field while another field has a certain value: ("auth", "login").
    # Purely for the page: a hidden field is still saved and still validated.
    show_if: tuple = ()

    def __post_init__(self):
        if self.kind == "password":
            self.secret = True


@dataclass
class SyncResult:
    """What a sync did. The counts and message are shown in the run history."""
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list = dc_field(default_factory=list)
    message: str = ""

    def summary(self):
        parts = [f"{self.created} created", f"{self.updated} updated", f"{self.skipped} unchanged"]
        if self.errors:
            parts.append(f"{len(self.errors)} errors")
        text = ", ".join(parts)
        return f"{self.message} ({text})" if self.message else text


class Integration:
    """Subclass this, fill in the attributes and implement ``test`` and ``sync``.

    ``config`` passed to both methods is a plain dict: every field name mapped to its saved
    value (secrets already decrypted, checkboxes as bool, numbers as int, missing values as
    the field default or "").
    """
    key = ""           # short id used in URLs and the database, e.g. "netbox"
    name = ""          # shown in the UI, e.g. "NetBox"
    description = ""   # one sentence: what it does
    icon = "plug"      # Bootstrap icon name
    docs = ""          # optional file name under documentation/integrations/
    fields = []        # list of Field
    can_sync = True    # False for integrations that only react to events

    def test(self, config):
        """Check that the settings work. Return a short success message or raise IntegrationError."""
        raise NotImplementedError

    def sync(self, config):
        """Do the work. Return a SyncResult or raise IntegrationError."""
        raise NotImplementedError
