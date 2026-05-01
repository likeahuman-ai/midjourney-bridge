"""Typed exceptions for midjourney-bridge."""

from __future__ import annotations


class MJError(Exception):
    """Base exception for all midjourney-bridge failures."""

    def __init__(self, message: str, *, status: int | None = None, body: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class SessionExpiredError(MJError):
    """Cookie is missing, expired, or rejected by Midjourney/Cloudflare.

    Recovery: re-paste the session cookie via ``mj cookie set``.
    """


class RateLimitedError(MJError):
    """Midjourney rate-limited this request."""


class CloudflareBlockedError(MJError):
    """Cloudflare returned a challenge / 403 — usually TLS fingerprint or cookie issue."""
