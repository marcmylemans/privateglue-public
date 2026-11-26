"""One-time codes (TOTP, RFC 6238), the kind an authenticator app shows.

Only the Python standard library is used. The secret is the Base32 text a site shows
under "can't scan the code?", or the ``secret=`` part of an ``otpauth://`` address.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import parse_qs, quote, unquote, urlparse

ALGORITHMS = {"SHA1": hashlib.sha1, "SHA256": hashlib.sha256, "SHA512": hashlib.sha512}


class InvalidSecret(ValueError):
    pass


def random_secret(length=32):
    """A new Base32 secret (32 characters is 160 bits, what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(length * 5 // 8)).decode("ascii").rstrip("=")


def normalize_secret(secret):
    """Tidy a secret as people paste it (spaces, dashes, lower case). Raises InvalidSecret."""
    cleaned = "".join((secret or "").split()).replace("-", "").upper().rstrip("=")
    if not cleaned:
        raise InvalidSecret("The secret is empty.")
    try:
        _decode(cleaned)
    except Exception:
        raise InvalidSecret("That is not a valid secret. It should only have the letters A to Z and the digits 2 to 7.")
    return cleaned


def _decode(secret):
    padded = secret + "=" * (-len(secret) % 8)
    return base64.b32decode(padded, casefold=True)


def parse(value):
    """Read what was pasted: a plain secret or a whole ``otpauth://totp/...`` address.

    Returns {"secret", "digits", "period", "algorithm", "issuer", "account"}.
    """
    value = (value or "").strip()
    settings = {"digits": 6, "period": 30, "algorithm": "SHA1", "issuer": "", "account": ""}
    if value.lower().startswith("otpauth://"):
        url = urlparse(value)
        if url.netloc.lower() != "totp":
            raise InvalidSecret("Only time-based codes (totp) are supported.")
        query = parse_qs(url.query)
        label = unquote(url.path.lstrip("/"))
        issuer, _, account = label.rpartition(":")
        settings["issuer"] = (query.get("issuer", [issuer])[0] or issuer).strip()
        settings["account"] = account.strip()
        try:
            settings["digits"] = int(query.get("digits", ["6"])[0])
            settings["period"] = int(query.get("period", ["30"])[0])
        except ValueError:
            raise InvalidSecret("The address has a digits or period value that is not a number.")
        settings["algorithm"] = query.get("algorithm", ["SHA1"])[0].upper()
        value = query.get("secret", [""])[0]
    if settings["digits"] not in (6, 7, 8) or not 5 <= settings["period"] <= 300:
        raise InvalidSecret("Unsupported number of digits or period.")
    if settings["algorithm"] not in ALGORITHMS:
        raise InvalidSecret("Unsupported algorithm.")
    settings["secret"] = normalize_secret(value)
    return settings


def code(secret, at=None, digits=6, period=30, algorithm="SHA1"):
    """The code valid at time ``at`` (seconds since 1970, default now)."""
    counter = int((time.time() if at is None else at) // period)
    digest = hmac.new(_decode(normalize_secret(secret)), struct.pack(">Q", counter),
                      ALGORITHMS[algorithm.upper()]).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % (10 ** digits)).zfill(digits)


def seconds_left(at=None, period=30):
    """How long the current code is still valid."""
    now = time.time() if at is None else at
    return int(period - (now % period)) or period


def verify(secret, candidate, at=None, window=1, digits=6, period=30, algorithm="SHA1"):
    """Is ``candidate`` right? Accepts the codes ``window`` steps before and after as well,
    because clocks differ a little. Returns the matching time step (so the caller can refuse
    a code that was already used) or None."""
    candidate = "".join(str(candidate or "").split())
    if len(candidate) != digits or not candidate.isdigit():
        return None
    now = time.time() if at is None else at
    for step in range(-window, window + 1):
        moment = now + step * period
        if hmac.compare_digest(code(secret, moment, digits, period, algorithm), candidate):
            return int(moment // period)
    return None


def provisioning_uri(secret, account, issuer):
    """The ``otpauth://`` address an authenticator app reads from a QR code."""
    label = quote(f"{issuer}:{account}", safe="")
    return (f"otpauth://totp/{label}?secret={normalize_secret(secret)}"
            f"&issuer={quote(issuer, safe='')}&algorithm=SHA1&digits=6&period=30")
