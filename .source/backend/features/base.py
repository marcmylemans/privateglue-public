"""The base class every feature builds on. See ``backend/features/__init__.py``."""


class Feature:
    #: Short lowercase name, the same as the package folder. Used in file paths.
    key = ""
    #: Name for people, used in messages.
    name = ""
    #: Where this feature's pieces go on a page that several features add to. Lower is first.
    order = 100
    #: A different place for one slot only: {"credential_view_login_bottom": 15}. For a piece
    #: that belongs next to something another feature's piece would otherwise push away.
    slot_order = None
    #: A Flask blueprint with the feature's own pages, or None.
    blueprint = None
    #: Extra columns on existing tables: {"credential": {"address": "TEXT"}}. The model
    #: needs the same column. New tables do not go here, they are created by themselves.
    columns = None

    def init_app(self, app):
        """Called once at start-up, after the blueprint is registered."""

    # --- credentials ---------------------------------------------------------------------
    def credential_validate(self, form, credential):
        """Check the posted form. ``credential`` is None for a new one. Return a list of
        messages; anything in it stops the save."""
        return []

    def credential_saved(self, credential, form, created, password_changed, old_password):
        """The credential is filled in and has an id, the transaction is still open: store
        what belongs to it with db.session, do not commit. ``old_password`` is the previous
        password in plain text when ``password_changed`` on an edit, otherwise None."""

    def credential_viewed(self, credential):
        """Someone opened the credential page (the password is on that page)."""

    def credential_deleted(self, credential):
        """About to be deleted, same transaction: remove what belongs to it."""

    def credential_query(self, query, args):
        """Narrow the credential list. ``args`` is request.args. Return the query."""
        return query

    # --- devices -------------------------------------------------------------------------
    def device_validate(self, form, device):
        return []

    def device_saved(self, device, form, created):
        """Saved from the device form (not from an import or a sync). Same rules as
        ``credential_saved``."""

    def device_viewed(self, device):
        pass

    def device_deleted(self, device):
        """About to be deleted, same transaction."""

    # --- notes (a note is a file, known by its file name such as "Router.md") -------------
    def note_saved(self, filename, form, created):
        pass

    def note_deleted(self, filename):
        pass

    # --- users ---------------------------------------------------------------------------
    def user_deleted(self, user):
        """About to be deleted, same transaction."""

    # --- everything worth remembering ------------------------------------------------------
    def audit_record(self, event):
        """Something happened that an activity log would list. ``event`` is a dict, see
        ``backend/utils/audit.py``."""

    # --- backups -------------------------------------------------------------------------
    def backup_files(self):
        """Extra files for a backup, as (path on disk, name inside the zip) pairs. Names
        must start with "files/<feature key>/"."""
        return []
