"""Proxy's REST API requires a signed-in Google account — sessions and their
history belong to whoever created them. The frontend sends the Google ID
token it got from sign-in as a Bearer token; every session/document route
depends on get_current_user to identify (and, for sessions, scope data to)
that account.
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from .services import google_auth


async def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in with Google to use Proxy")
    token = authorization.split(" ", 1)[1].strip()
    identity = google_auth.verify_id_token(token)
    if identity is None:
        raise HTTPException(status_code=401, detail="Your sign-in has expired — please sign in again")
    return identity
