"""Share links for one listing (2026-10-22, owner: "a share button in the bot and on the site that leads to Todira's
own page for the flat, not the original ad, with a way into the bot").

The link is /s/<id>-<signature>: the signature (keyed by SESSION_SECRET_KEY, which the website, bot and scraper all
have) means the page answers only for links Todira itself handed out, so nobody can walk /s/1, /s/2, ... and read
every listing without an account."""

from __future__ import annotations

import hashlib
import hmac
import os

SITE_URL = "https://todira.app"
_SIG_LEN = 10


def _secret() -> bytes:
    return os.environ.get("SESSION_SECRET_KEY", "dev-only-insecure-session-key").encode()


def _signature(listing_id: int) -> str:
    return hmac.new(_secret(), f"share:{listing_id}".encode(), hashlib.sha256).hexdigest()[:_SIG_LEN]


def share_token(listing_id: int) -> str:
    return f"{listing_id}-{_signature(listing_id)}"


def share_path(listing_id: int) -> str:
    return f"/s/{share_token(listing_id)}"


def share_url(listing_id: int) -> str:
    return SITE_URL + share_path(listing_id)


def listing_id_from_token(token: str) -> int | None:
    """The listing id a share token points at, or None when it is malformed or was not signed by us."""
    id_part, sep, sig = token.partition("-")
    if not sep or not id_part.isdigit() or len(id_part) > 12:
        return None
    listing_id = int(id_part)
    return listing_id if hmac.compare_digest(sig, _signature(listing_id)) else None
