"""Small HTTP helper so every integration fails the same, readable way."""
import requests

from backend.integrations.base import IntegrationError

DEFAULT_TIMEOUT = 20


def request_json(method, url, *, headers=None, params=None, json=None, verify=True,
                 timeout=DEFAULT_TIMEOUT, session=None, what="the server"):
    """Do one request and return the decoded JSON (None for an empty body).

    Turns network errors and HTTP error codes into IntegrationError with a message that
    names the system (``what``) and never includes tokens.
    """
    http = session or requests
    try:
        resp = http.request(method, url, headers=headers, params=params, json=json,
                            verify=verify, timeout=timeout)
    except requests.exceptions.SSLError:
        raise IntegrationError(
            f"Could not verify the TLS certificate of {what}. "
            "Use a trusted certificate or turn off certificate verification in the settings."
        )
    except requests.exceptions.ConnectionError:
        raise IntegrationError(f"Could not connect to {what}. Check the address and that it is reachable from this container.")
    except requests.exceptions.Timeout:
        raise IntegrationError(f"{what} did not answer within {timeout} seconds.")
    except requests.exceptions.RequestException as exc:
        raise IntegrationError(f"Request to {what} failed: {type(exc).__name__}")

    if resp.status_code in (401, 403):
        raise IntegrationError(f"{what} rejected the credentials (HTTP {resp.status_code}). Check the token and its permissions.")
    if resp.status_code == 404:
        raise IntegrationError(f"{what} answered 404 Not Found. Check the address.")
    if resp.status_code >= 400:
        raise IntegrationError(f"{what} answered with an error (HTTP {resp.status_code}).")
    if not resp.content:
        return None
    try:
        return resp.json()
    except ValueError:
        raise IntegrationError(f"{what} did not return JSON. Check the address.")
