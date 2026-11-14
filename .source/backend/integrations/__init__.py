"""Integrations: optional modules that connect PrivateGlue to other systems.

Each integration is one package in this folder (for example ``backend/integrations/netbox``)
that exposes a module-level ``INTEGRATION`` object, an instance of a subclass of
``Integration``. Packages are discovered automatically: adding a folder is enough, no
central list to edit. See ``documentation/integrations/README.md`` for the full guide.
"""
import importlib
import pkgutil

from backend.integrations.base import (  # noqa: F401  (re-exported for modules)
    Field,
    Integration,
    IntegrationError,
    SyncResult,
)

# Sub-modules of this package that are part of the framework, not integrations.
_FRAMEWORK_MODULES = {"base", "models", "devices", "runner", "scheduler", "http"}

_registry = None


def discover(force=False):
    """Import every integration package once and return {key: integration}."""
    global _registry
    if _registry is not None and not force:
        return _registry
    found = {}
    for info in pkgutil.iter_modules(__path__):
        if info.name in _FRAMEWORK_MODULES or info.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"{__name__}.{info.name}")
        except Exception as exc:  # one broken module must not take the app down
            print(f"[integrations] could not load '{info.name}': {exc}")
            continue
        integration = getattr(module, "INTEGRATION", None)
        if isinstance(integration, Integration) and integration.key:
            found[integration.key] = integration
    _registry = dict(sorted(found.items(), key=lambda kv: kv[1].name.lower()))
    return _registry


def get(key):
    return discover().get(key)


def register(integration):
    """Add an integration by hand. Used by tests."""
    discover()[integration.key] = integration
    return integration
