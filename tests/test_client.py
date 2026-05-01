"""Tests for midjourney_bridge.client — error mapping with mocked transport."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from midjourney_bridge.client import MJClient
from midjourney_bridge.errors import (
    CloudflareBlockedError,
    MJError,
    RateLimitedError,
    SessionExpiredError,
)
from midjourney_bridge.session import Session


def _mk_resp(status: int, *, json_body: Any | None = None, text: str = "") -> MagicMock:
    r = MagicMock()
    r.status_code = status
    if json_body is not None:
        r.json.return_value = json_body
        r.text = ""
    else:
        r.json.side_effect = ValueError("no json")
        r.text = text
    return r


def test_get_returns_parsed_json(fake_session: Session) -> None:
    client = MJClient(fake_session)
    with patch("midjourney_bridge.client.cc_requests.get") as mock_get:
        mock_get.return_value = _mk_resp(200, json_body={"data": [], "cursor": "c1"})
        result = client.get("/api/imagine", params={"page_size": 5})

    assert result == {"data": [], "cursor": "c1"}
    _, kwargs = mock_get.call_args
    assert kwargs["impersonate"] == "chrome120"
    assert kwargs["params"] == {"page_size": 5}
    assert "cookie" not in kwargs["headers"]  # cookies go separately, not in headers
    assert kwargs["headers"]["x-csrf-protection"] == "1"


def test_post_includes_origin_and_content_type(fake_session: Session) -> None:
    client = MJClient(fake_session)
    with patch("midjourney_bridge.client.cc_requests.post") as mock_post:
        mock_post.return_value = _mk_resp(200, json_body={"job_id": "abc"})
        client.post("/api/submit-jobs", json={"t": "imagine", "prompt": "test"})

    _, kwargs = mock_post.call_args
    assert kwargs["headers"]["content-type"] == "application/json"
    assert kwargs["headers"]["origin"] == "https://www.midjourney.com"
    assert kwargs["json"] == {"t": "imagine", "prompt": "test"}


def test_403_with_cloudflare_interstitial_raises_cloudflare_blocked(
    fake_session: Session,
) -> None:
    client = MJClient(fake_session)
    with patch("midjourney_bridge.client.cc_requests.get") as mock_get:
        mock_get.return_value = _mk_resp(
            403, text="<title>Just a moment...</title>challenges.cloudflare.com"
        )
        with pytest.raises(CloudflareBlockedError, match="TLS fingerprint or cookie"):
            client.get("/api/imagine")


def test_401_raises_session_expired(fake_session: Session) -> None:
    client = MJClient(fake_session)
    with patch("midjourney_bridge.client.cc_requests.get") as mock_get:
        mock_get.return_value = _mk_resp(401, text="unauthorized")
        with pytest.raises(SessionExpiredError, match="mj cookie set"):
            client.get("/api/imagine")


def test_429_raises_rate_limited(fake_session: Session) -> None:
    client = MJClient(fake_session)
    with patch("midjourney_bridge.client.cc_requests.get") as mock_get:
        mock_get.return_value = _mk_resp(429, text="slow down")
        with pytest.raises(RateLimitedError, match="rate-limited"):
            client.get("/api/imagine")


def test_500_raises_mj_error(fake_session: Session) -> None:
    client = MJClient(fake_session)
    with patch("midjourney_bridge.client.cc_requests.get") as mock_get:
        mock_get.return_value = _mk_resp(500, text="server error")
        with pytest.raises(MJError, match="500"):
            client.get("/api/imagine")


def test_array_response_wrapped_in_data(fake_session: Session) -> None:
    """Some endpoints return bare arrays — we wrap so layer 2 sees a consistent dict."""
    client = MJClient(fake_session)
    with patch("midjourney_bridge.client.cc_requests.get") as mock_get:
        mock_get.return_value = _mk_resp(200, json_body=[1, 2, 3])
        result = client.get("/api/something")
    assert result == {"data": [1, 2, 3]}


def test_user_id_passthrough(fake_session: Session) -> None:
    client = MJClient(fake_session)
    assert client.user_id == fake_session.user_id == "test-user-123"
