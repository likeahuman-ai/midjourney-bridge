"""Shared test fixtures."""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator

import pytest

from midjourney_bridge.session import Session


def _fake_jwt(user_id: str = "test-user-123") -> str:
    """Build a fake unsigned JWT with the bare minimum for our session loader."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).rstrip(b"=").decode()
    payload = (
        base64.urlsafe_b64encode(json.dumps({"midjourney_id": user_id, "exp": 9999999999}).encode())
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}.fake-signature"


@pytest.fixture
def fake_session() -> Session:
    """A Session with a fake but structurally valid cookie + JWT."""
    jwt = _fake_jwt()
    cookie = (
        f"__Host-Midjourney.AuthUserTokenV3_i={jwt}; "
        f"__Host-Midjourney.AuthUserTokenV3_r=fake-refresh-token; "
        f"cf_clearance=fake-cf-clearance"
    )
    return Session(
        cookie=cookie,
        user_agent="Mozilla/5.0 (test) Chrome/147.0",
        user_id="test-user-123",
    )


@pytest.fixture
def isolated_config(tmp_path, monkeypatch) -> Iterator[None]:
    """Point the config dir to a tmp path so tests don't touch real config."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    yield
