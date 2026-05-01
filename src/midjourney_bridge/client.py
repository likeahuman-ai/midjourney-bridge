"""Layer 1 transport: Chrome-impersonated HTTP client for midjourney.com.

Why curl_cffi: both /api/* and cdn.midjourney.com enforce TLS fingerprinting (JA3/JA4)
via Cloudflare. Plain `requests`, `httpx`, `urllib3`, even Node's `undici` get a 403
challenge. curl_cffi statically links boringssl + a Chrome-style TLS handshake, so the
server can't distinguish us from a real browser.
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urljoin

from curl_cffi import requests as cc_requests

from midjourney_bridge.errors import (
    CloudflareBlockedError,
    MJError,
    RateLimitedError,
    SessionExpiredError,
)
from midjourney_bridge.session import Session

API_BASE = "https://www.midjourney.com"
CDN_BASE = "https://cdn.midjourney.com"

# curl_cffi requires this be one of its known impersonation literals.
# We pin to chrome120 — verified working against MJ's Cloudflare config in the spike.
IMPERSONATE: Literal["chrome120"] = "chrome120"

# Headers required on every request. Static — no rotation needed.
_BASE_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "x-csrf-protection": "1",
}


class MJClient:
    """Chrome-impersonated HTTP client for midjourney.com.

    Holds a Session (cookie + UA + user_id) and exposes ``get`` / ``post`` helpers
    that auto-attach auth, parse JSON, and map errors to typed exceptions.

    Layer 2 (``midjourney_bridge.api``) sits on top of this and provides typed methods
    like ``list_jobs`` / ``imagine`` / ``upscale``.
    """

    def __init__(self, session: Session, *, timeout: float = 30.0) -> None:
        self.session = session
        self.timeout = timeout

    @property
    def user_id(self) -> str:
        return self.session.user_id

    def _headers(self, *, referer: str = f"{API_BASE}/organize") -> dict[str, str]:
        return {
            **_BASE_HEADERS,
            "user-agent": self.session.user_agent,
            "referer": referer,
        }

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        referer: str | None = None,
    ) -> dict[str, Any]:
        """GET a JSON endpoint. Returns parsed JSON dict."""
        url = urljoin(API_BASE, path)
        resp = cc_requests.get(
            url,
            params=params,
            headers=self._headers(referer=referer or f"{API_BASE}/organize"),
            cookies=self.session.cookie_dict,
            impersonate=IMPERSONATE,
            timeout=self.timeout,
        )
        return self._parse(resp)

    def post(
        self,
        path: str,
        *,
        json: dict[str, Any],
        referer: str | None = None,
    ) -> dict[str, Any]:
        """POST a JSON body to an endpoint. Returns parsed JSON dict."""
        url = urljoin(API_BASE, path)
        resp = cc_requests.post(
            url,
            json=json,
            headers={
                **self._headers(referer=referer or f"{API_BASE}/imagine"),
                "content-type": "application/json",
                "origin": API_BASE,
            },
            cookies=self.session.cookie_dict,
            impersonate=IMPERSONATE,
            timeout=self.timeout,
        )
        return self._parse(resp)

    def _parse(self, resp: Any) -> dict[str, Any]:
        """Map an HTTP response to a JSON dict or raise a typed error."""
        status = resp.status_code

        if status == 200:
            try:
                parsed: Any = resp.json()
            except Exception as e:
                raise MJError(
                    f"non-JSON 200 response: {resp.text[:200]!r}",
                    status=status,
                ) from e
            if not isinstance(parsed, dict):
                # Some endpoints return arrays — wrap them so our return type stays a dict.
                # Layer 2 handles this case explicitly when needed.
                return {"data": parsed}
            return parsed

        body_preview = resp.text[:300] if resp.text else "<empty>"

        if status == 401 or status == 403:
            # 403 with the Cloudflare interstitial means TLS/cookie issue.
            if "Just a moment" in resp.text or "challenges.cloudflare.com" in resp.text:
                raise CloudflareBlockedError(
                    "Cloudflare blocked the request (TLS fingerprint or cookie). "
                    "If you're sure curl_cffi impersonate=chrome120 is in use, "
                    "your cookie probably expired — run `mj cookie set`.",
                    status=status,
                    body=body_preview,
                )
            raise SessionExpiredError(
                f"session rejected ({status}). Run `mj cookie set` to refresh.",
                status=status,
                body=body_preview,
            )

        if status == 429:
            raise RateLimitedError(
                "Midjourney rate-limited the request. Back off and retry.",
                status=status,
                body=body_preview,
            )

        raise MJError(
            f"unexpected response {status}: {body_preview}",
            status=status,
            body=body_preview,
        )
