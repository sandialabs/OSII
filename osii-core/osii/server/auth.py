"""Password credentials map to stable accounts; authorization uses principals."""
from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request


hasher = PasswordHasher()
_dummy_hash = hasher.hash(secrets.token_urlsafe(32))
COOKIE = "osii_session"
CSRF_COOKIE = "osii_csrf"
ROLES = {"reader": 0, "curator": 1, "admin": 2}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(value: str) -> str:
    if not 15 <= len(value) <= 128:
        raise ValueError("Passwords must contain 15 to 128 characters")
    return hasher.hash(value)


def verify(encoded: str | None, password: str) -> bool:
    try:
        return hasher.verify(encoded or _dummy_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def public_account(account: dict) -> dict:
    return {k: account[k] for k in ("id", "username", "role", "active", "must_change_password")}


def origin_check(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in request.app.state.settings.origins:
        raise HTTPException(403, "Untrusted request origin")


def require(role: str = "reader", *, password_change: bool = False):
    def principal(request: Request) -> dict:
        token = request.cookies.get(COOKIE, "")
        account = request.app.state.store.session(digest(token)) if token else None
        if not account:
            raise HTTPException(401, "Sign in is required")
        if account["must_change_password"] and not password_change:
            raise HTTPException(403, "Change your temporary password before using the library")
        if ROLES.get(account["role"], -1) < ROLES[role]:
            raise HTTPException(403, "This action is not allowed for your account")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin_check(request)
            csrf = request.headers.get("X-CSRF-Token", "")
            if not csrf or not secrets.compare_digest(digest(csrf), account["csrf_hash"]):
                raise HTTPException(403, "Invalid CSRF token")
        return account
    return principal
