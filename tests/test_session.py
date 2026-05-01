"""Tests for midjourney_bridge.session — cookie loading + JWT decoding."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from midjourney_bridge import session as sess


def _make_jwt(user_id: str = "abc-123") -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    payload = (
        base64.urlsafe_b64encode(json.dumps({"midjourney_id": user_id, "exp": 9999999999}).encode())
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}.sig"


def test_extract_user_id_from_jwt() -> None:
    jwt = _make_jwt("test-user-xyz")
    cookie = f"__Host-Midjourney.AuthUserTokenV3_i={jwt}; other=stuff"
    assert sess._extract_user_id(cookie) == "test-user-xyz"


def test_extract_user_id_missing_jwt_raises() -> None:
    with pytest.raises(ValueError, match="AuthUserTokenV3_i"):
        sess._extract_user_id("just=some; other=cookies")


def test_extract_user_id_malformed_jwt_raises() -> None:
    cookie = "__Host-Midjourney.AuthUserTokenV3_i=not.a.valid.jwt.at.all"
    with pytest.raises(ValueError):
        sess._extract_user_id(cookie)


def test_load_from_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    jwt = _make_jwt("env-user")
    cookie = f"__Host-Midjourney.AuthUserTokenV3_i={jwt}"
    monkeypatch.setenv("MJ_COOKIE", cookie)
    monkeypatch.setenv("MJ_UA", "TestUA/1.0")

    s = sess.load(env_file=Path("/nonexistent/.env"))
    assert s.user_id == "env-user"
    assert s.user_agent == "TestUA/1.0"


def test_load_missing_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MJ_COOKIE", raising=False)
    with pytest.raises(FileNotFoundError, match="MJ_COOKIE"):
        sess.load(env_file=tmp_path / "nope.env")


def test_session_cookie_dict_parses() -> None:
    s = sess.Session(
        cookie="a=1; b=two; c=three=four",
        user_agent="ua",
        user_id="u",
    )
    d = s.cookie_dict
    assert d["a"] == "1"
    assert d["b"] == "two"
    assert d["c"] == "three=four"  # values can contain = (e.g. base64)
