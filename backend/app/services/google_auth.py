"""Shared Google ID token verification — used both by the Meet websocket
(routers/meet_ws.py) and Proxy's REST API (auth.py), so there is exactly one
place that talks to Google's public keys.
"""

from __future__ import annotations

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from .. import config

_request = google_requests.Request()


def verify_id_token(token: str) -> dict | None:
    """Returns {"email", "name", "picture"} for a valid token, else None."""
    if not token or not config.GOOGLE_CLIENT_ID:
        return None
    try:
        claims = google_id_token.verify_oauth2_token(token, _request, config.GOOGLE_CLIENT_ID)
    except Exception:  # noqa: BLE001 - any verification failure means "not signed in"
        return None
    email = claims.get("email")
    if not email:
        return None
    return {
        "email": email,
        "name": str(claims.get("name") or email).strip(),
        "picture": claims.get("picture"),
    }
