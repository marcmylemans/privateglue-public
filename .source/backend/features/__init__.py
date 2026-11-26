"""Features: optional parts of PrivateGlue that plug into the existing pages.

Each feature is one package in this folder (for example ``backend/features/tags``) that
exposes a module-level ``FEATURE`` object, an instance of a subclass of ``Feature``.
Packages are found automatically: adding a folder is enough, no central list to edit.
That keeps features apart from each other, so two of them can be built at the same time
without touching the same files.

A feature can bring:

* its own database tables: models defined in the package are created at start-up;
* extra columns on an existing table: ``columns = {"credential": {"address": "TEXT"}}``;
* its own pages: ``blueprint = Blueprint(...)``;
* pieces of an existing page: a template ``backend/templates/features/<key>/<slot>.html``
  is included wherever the page has ``{% for tpl in feature_templates('<slot>') %}``;
* a script and a stylesheet, loaded on every page when they exist:
  ``backend/static/js/features/<key>.js`` and ``backend/static/css/features/<key>.css``;
* reactions to what happens in the app: the hook methods on ``Feature`` below.

Templates reach a feature's own helpers through ``feat``: ``feat.tags.for_credential(c)``.
See ``documentation/FEATURES.md`` for the slots and the rules.
"""
import importlib
import os
import pkgutil

from flask import current_app

from backend.features.base import Feature  # noqa: F401  (re-exported for feature packages)

_FRAMEWORK_MODULES = {"base"}

_registry = None


def discover(force=False):
    """Import every feature package once and return {key: feature}, lowest ``order`` first."""
    global _registry
    if _registry is not None and not force:
        return _registry
    found = {}
    for info in pkgutil.iter_modules(__path__):
        if info.name in _FRAMEWORK_MODULES or info.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"{__name__}.{info.name}")
        except Exception as exc:  # one broken feature must not take the app down
            print(f"[features] could not load '{info.name}': {type(exc).__name__}: {exc}")
            continue
        feature = getattr(module, "FEATURE", None)
        if isinstance(feature, Feature) and feature.key:
            found[feature.key] = feature
    _registry = _sorted(found)
    return _registry


def _sorted(found):
    return dict(sorted(found.items(), key=lambda kv: (kv[1].order, kv[0])))


def all_features():
    return list(discover().values())


def get(key):
    return discover().get(key)


def register(feature):
    """Add a feature by hand. Used by tests."""
    global _registry
    found = dict(discover())
    found[feature.key] = feature
    _registry = _sorted(found)
    return feature


def unregister(key):
    """Remove a feature added by hand. Used by tests."""
    discover().pop(key, None)


class _FeatureLookup:
    """``feat.<key>`` in templates. An unknown key gives None instead of an error, so a
    template never breaks a page because a feature is missing."""

    def __getattr__(self, key):
        return get(key)

    def __getitem__(self, key):
        return get(key)

    def __contains__(self, key):
        return get(key) is not None


def init_app(app):
    """Wire the features into a Flask app: pages, template helpers and their own set-up."""
    for feature in all_features():
        if feature.blueprint is not None and feature.blueprint.name not in app.blueprints:
            app.register_blueprint(feature.blueprint)
        feature.init_app(app)
    app.jinja_env.globals["feature_templates"] = templates
    app.jinja_env.globals["feature_assets"] = assets
    app.jinja_env.globals["feat"] = _FeatureLookup()


def templates(slot):
    """Templates to include at a slot, in feature order. Only files that exist count."""
    loader = current_app.jinja_env.loader
    known = set(loader.list_templates()) if current_app.testing else _template_names(current_app)
    found = []
    for feature in all_features():
        name = f"features/{feature.key}/{slot}.html"
        if name in known:
            found.append(((feature.slot_order or {}).get(slot, feature.order), feature.key, name))
    return [name for _, _, name in sorted(found)]


def _template_names(app):
    names = app.extensions.get("pg_feature_templates")
    if names is None:
        names = {n for n in app.jinja_env.loader.list_templates() if n.startswith("features/")}
        app.extensions["pg_feature_templates"] = names
    return names


def assets(kind):
    """Static paths (for url_for('static', filename=...)) of each feature's script or stylesheet."""
    folder = current_app.static_folder
    out = []
    for feature in all_features():
        relative = f"{kind}/features/{feature.key}.{kind}"
        if folder and os.path.isfile(os.path.join(folder, relative)):
            out.append(relative)
    return out


# --- hooks -------------------------------------------------------------------------------

def _failed(feature, hook, exc):
    # In tests a failing hook is a bug to see at once. In production one broken feature
    # must not stop people from saving a device or a credential.
    if current_app and current_app.testing:
        raise exc
    print(f"[features] {feature.key}.{hook} failed: {type(exc).__name__}: {exc}")


def emit(hook, *args, **kwargs):
    """Tell every feature that something happened."""
    for feature in all_features():
        try:
            getattr(feature, hook)(*args, **kwargs)
        except Exception as exc:
            _failed(feature, hook, exc)


def problems(hook, *args, **kwargs):
    """Ask every feature to check a form. Returns the messages to show; empty means fine."""
    found = []
    for feature in all_features():
        try:
            found.extend(getattr(feature, hook)(*args, **kwargs) or [])
        except Exception as exc:
            _failed(feature, hook, exc)
    return found


def refine(hook, value, *args, **kwargs):
    """Pass a value (a database query, for example) through every feature in turn."""
    for feature in all_features():
        try:
            result = getattr(feature, hook)(value, *args, **kwargs)
        except Exception as exc:
            _failed(feature, hook, exc)
            continue
        if result is not None:
            value = result
    return value


def upgrade_columns(connection, table_columns):
    """Add the extra columns features declared, on tables that already exist.

    ``table_columns(table)`` returns the current column names, or an empty list when the
    table does not exist yet (then create_all() makes it complete and nothing is needed).
    Returns the list of "table.column" that were added.
    """
    added = []
    for feature in all_features():
        for table, columns in (feature.columns or {}).items():
            existing = table_columns(table)
            if not existing:
                continue
            for column, definition in columns.items():
                if column in existing:
                    continue
                if not (_plain(table) and _plain(column)):
                    raise ValueError(f"Feature '{feature.key}' declares an unsafe column name.")
                connection.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')
                existing.append(column)
                added.append(f"{table}.{column}")
    return added


def _plain(name):
    return bool(name) and name.replace("_", "").isalnum()
