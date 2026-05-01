"""End-to-end smoke test: load real cookie, ping MJ, print account info.

This is the precursor to the `mj doctor` CLI command. Hits the network — only run
manually with a valid cookie configured.

Usage:
    uv run python scripts/doctor.py

Or with an explicit env file:
    MJ_COOKIE_FILE=/path/to/.env uv run python scripts/doctor.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from midjourney_bridge.client import MJClient
from midjourney_bridge.errors import MJError
from midjourney_bridge.session import env_path, load


def _redact(s: str, keep: int = 8) -> str:
    if len(s) <= keep * 2:
        return "***"
    return f"{s[:keep]}…{s[-keep:]} ({len(s)} chars)"


def main() -> int:
    env_file_str = os.environ.get("MJ_COOKIE_FILE")
    env_file = Path(env_file_str) if env_file_str else env_path()

    print(f"config: {env_file}")
    print(f"exists: {env_file.exists()}")

    try:
        session = load(env_file=env_file)
    except (FileNotFoundError, ValueError) as e:
        print(f"\n✗ session load failed: {e}", file=sys.stderr)
        return 1

    print(f"user_id: {session.user_id}")
    print(f"cookie:  {_redact(session.cookie)}")
    print(f"ua:      {session.user_agent}")

    client = MJClient(session)
    try:
        # /api/imagine is the cheapest read; just ask for 1 job
        result = client.get(
            "/api/imagine",
            params={"user_id": session.user_id, "page_size": 1},
        )
    except MJError as e:
        print(f"\n✗ API call failed: {e} (status={e.status})", file=sys.stderr)
        return 1

    jobs = result.get("data", [])
    print(f"\n✓ API ok — {len(jobs)} job(s) returned")
    if jobs:
        first = jobs[0]
        prompt = (first.get("full_command") or "")[:60]
        print(f"  most recent job: {first.get('id')}")
        print(f"  prompt:          {prompt!r}…")

    return 0


if __name__ == "__main__":
    sys.exit(main())
