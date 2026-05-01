"""Tests for midjourney_bridge.extract — browser cookie auto-extraction."""

from __future__ import annotations

from http.cookiejar import Cookie, CookieJar
from unittest.mock import patch

import pytest

from midjourney_bridge.extract import (
    REQUIRED_AUTH,
    ExtractedSession,
    ExtractionError,
    build_user_agent,
    detect_chrome_version,
    extract,
    supported_browsers,
)


def _make_cookie(name: str, value: str = "x", domain: str = ".midjourney.com") -> Cookie:
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=True,
        domain_initial_dot=domain.startswith("."),
        path="/",
        path_specified=True,
        secure=True,
        expires=None,
        discard=False,
        comment=None,
        comment_url=None,
        rest={},
    )


def _jar_with(*names: str) -> CookieJar:
    jar = CookieJar()
    for n in names:
        jar.set_cookie(_make_cookie(n))
    return jar


def test_supported_browsers_lists_majors() -> None:
    browsers = supported_browsers()
    assert "chrome" in browsers
    assert "firefox" in browsers
    assert "edge" in browsers


def test_extract_succeeds_on_first_browser_with_required_cookie() -> None:
    chrome_jar = _jar_with(REQUIRED_AUTH, "cf_clearance", "__cf_bm")
    with patch(
        "midjourney_bridge.extract._try_browser",
        side_effect=lambda name: chrome_jar if name == "chrome" else None,
    ):
        result = extract()
    assert isinstance(result, ExtractedSession)
    assert result.browser == "chrome"
    assert REQUIRED_AUTH in result.cookie_names
    assert "cf_clearance" in result.cookie_names
    # Cookie string contains all names
    assert REQUIRED_AUTH in result.cookie
    assert "cf_clearance" in result.cookie


def test_extract_falls_back_to_next_browser() -> None:
    """If chrome fails (no jar), try brave; if brave has no required cookie, try arc, etc."""
    arc_jar = _jar_with(REQUIRED_AUTH, "cf_clearance")
    brave_jar_no_auth = _jar_with("cf_clearance")  # missing required

    def fake_try(name: str) -> CookieJar | None:
        if name == "chrome":
            return None  # not installed
        if name == "brave":
            return brave_jar_no_auth  # logged out / wrong account
        if name == "arc":
            return arc_jar  # winner
        return None

    with patch("midjourney_bridge.extract._try_browser", side_effect=fake_try):
        result = extract()
    assert result.browser == "arc"


def test_extract_with_explicit_browser() -> None:
    edge_jar = _jar_with(REQUIRED_AUTH)
    with patch(
        "midjourney_bridge.extract._try_browser",
        side_effect=lambda n: edge_jar if n == "edge" else None,
    ):
        result = extract(browser="edge")
    assert result.browser == "edge"


def test_extract_explicit_browser_failure_raises() -> None:
    with (
        patch("midjourney_bridge.extract._try_browser", return_value=None),
        pytest.raises(ExtractionError, match="Tried"),
    ):
        extract(browser="firefox")


def test_extract_all_browsers_fail_raises_with_summary() -> None:
    with (
        patch("midjourney_bridge.extract._try_browser", return_value=None),
        pytest.raises(ExtractionError) as exc_info,
    ):
        extract()
    msg = str(exc_info.value)
    assert "chrome" in msg
    assert "firefox" in msg
    assert "logged in to midjourney.com" in msg


def test_extract_filters_non_mj_domains_out_of_jar() -> None:
    """Defensive: even if the jar somehow has cross-domain cookies, we strip them."""
    jar = CookieJar()
    jar.set_cookie(_make_cookie(REQUIRED_AUTH, domain=".midjourney.com"))
    jar.set_cookie(_make_cookie("evil_cookie", domain=".attacker.com"))
    with patch(
        "midjourney_bridge.extract._try_browser",
        side_effect=lambda n: jar if n == "chrome" else None,
    ):
        result = extract()
    assert "evil_cookie" not in result.cookie


def test_build_user_agent_default() -> None:
    ua = build_user_agent()
    assert ua.startswith("Mozilla/5.0")
    assert "Chrome/" in ua
    assert "Safari/537.36" in ua


def test_build_user_agent_with_explicit_version() -> None:
    ua = build_user_agent(version="123.0.4567.890")
    assert "Chrome/123.0.0.0" in ua  # major-only reduced UA


def test_detect_chrome_version_returns_str_or_none() -> None:
    """Smoke test — actually run on this machine; either returns a version or None."""
    v = detect_chrome_version()
    assert v is None or isinstance(v, str)
    if v is not None:
        # Should be dotted version
        assert "." in v
