"""Anonymous owner identity: a random id in an HMAC-signed HttpOnly cookie (spec 8). A bad signature means a new owner,
never access to the old one's resources."""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from typing import Optional

COOKIE = "oa_owner"


def new_owner() -> str:
    return uuid.uuid4().hex


def _mac(owner: str, secret: bytes) -> str:
    digest = hmac.new(secret, owner.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def sign(owner: str, secret: bytes) -> str:
    return f"{owner}.{_mac(owner, secret)}"


def verify(token: Optional[str], secret: bytes) -> Optional[str]:
    if not token or token.count(".") != 1:
        return None
    owner, mac = token.split(".")
    if not owner or not hmac.compare_digest(mac, _mac(owner, secret)):
        return None
    return owner
