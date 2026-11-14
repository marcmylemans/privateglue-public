"""Small security helpers shared by the routes."""
import hmac
from urllib.parse import urlsplit

from flask import request


def is_safe_redirect_target(target):
    """True when ``target`` is a path on this site.

    Rejects absolute URLs, scheme-relative URLs ("//evil.example") and the backslash
    variants browsers treat the same way ("/\\evil.example"), plus control characters.
    """
    if not target or not isinstance(target, str):
        return False
    if any(ord(c) < 0x20 for c in target) or "\\" in target:
        return False
    if not target.startswith("/") or target.startswith("//"):
        return False
    parts = urlsplit(target)
    return not parts.scheme and not parts.netloc


def same_site_referrer():
    """The Referer header as a local path, or None when it points to another site."""
    ref = request.referrer
    if not ref:
        return None
    parts = urlsplit(ref)
    if parts.netloc and parts.netloc != request.host:
        return None
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return path if is_safe_redirect_target(path) else None


def constant_time_equals(a, b):
    """Compare two secrets without leaking how many leading characters match."""
    if a is None or b is None:
        return False
    return hmac.compare_digest(str(a).encode(), str(b).encode())
