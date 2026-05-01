"""Session config: load cookie + UA from env, decode JWT to extract user_id.

This is a minimal stub for M1.P1. Full archive/doctor/refresh logic comes in P2.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values
from platformdirs import user_config_dir

CONFIG_APP = "mj-bridge"  # stable storage name — never changes with package renames
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class Session:
    """A loaded MJ session: cookie string, UA, and decoded user_id."""

    cookie: str
    user_agent: str
    user_id: str

    @property
    def cookie_dict(self) -> dict[str, str]:
        """Parse cookie string into a name→value dict for curl_cffi."""
        out: dict[str, str] = {}
        for chunk in self.cookie.split("; "):
            if "=" in chunk:
                k, _, v = chunk.partition("=")
                out[k.strip()] = v
        return out


def config_path() -> Path:
    """Return the OS-native config directory for midjourney-bridge."""
    return Path(user_config_dir(CONFIG_APP))


def env_path() -> Path:
    """Return the path to the .env file holding the cookie."""
    return config_path() / ".env"


def _decode_jwt_payload(jwt: str) -> dict[str, object]:
    """Decode a JWT payload (no signature verification — we trust MJ's own cookie)."""
    parts = jwt.split(".")
    if len(parts) != 3:
        raise ValueError("malformed JWT")
    payload_b64 = parts[1]
    # urlsafe base64 may be unpadded
    payload_b64 += "=" * (-len(payload_b64) % 4)
    payload_bytes = base64.urlsafe_b64decode(payload_b64)
    decoded: dict[str, object] = json.loads(payload_bytes)
    return decoded


def _extract_user_id(cookie_str: str) -> str:
    """Pull `midjourney_id` out of the JWT inside the session cookie."""
    cookies = dict(kv.split("=", 1) for kv in cookie_str.split("; ") if "=" in kv)
    jwt = cookies.get("__Host-Midjourney.AuthUserTokenV3_i")
    if not jwt:
        raise ValueError(
            "cookie does not contain __Host-Midjourney.AuthUserTokenV3_i — "
            "did you copy the full cookie value from devtools?"
        )
    payload = _decode_jwt_payload(jwt)
    user_id = payload.get("midjourney_id")
    if not isinstance(user_id, str):
        raise ValueError("JWT payload missing midjourney_id")
    return user_id


def load(env_file: Path | None = None) -> Session:
    """Load a Session from the user config dir, or a custom .env path."""
    path = env_file or env_path()
    if path.exists():
        env: dict[str, str | None] = dict(dotenv_values(path))
    else:
        env = {}

    # Allow direct env var override for CI/tests
    cookie = os.environ.get("MJ_COOKIE") or env.get("MJ_COOKIE") or ""
    ua = os.environ.get("MJ_UA") or env.get("MJ_UA") or DEFAULT_UA

    if not cookie:
        raise FileNotFoundError(
            f"No MJ_COOKIE found in {path} or environment. Run `mj cookie set` to configure."
        )

    user_id = _extract_user_id(cookie)
    return Session(cookie=cookie, user_agent=ua, user_id=user_id)
