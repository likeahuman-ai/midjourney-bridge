"""Integration tests — hit the real Midjourney API.

Run only with: ``uv run pytest -m integration``
or via:        ``./scripts/check.sh --integration``

Skipped by default. Each test requires a working session (``mj cookie auto`` must
have run successfully on this machine, OR ``MJ_COOKIE`` env var must be set).
"""

from __future__ import annotations

import pytest

from midjourney_bridge import api
from midjourney_bridge.client import MJClient
from midjourney_bridge.errors import MJError, SessionExpiredError
from midjourney_bridge.session import load

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def real_client() -> MJClient:
    """A real MJClient using whatever session is configured locally.

    Skips the test module if no valid session is available.
    """
    try:
        session = load()
    except (FileNotFoundError, ValueError) as e:
        pytest.skip(f"no MJ session configured: {e}")
    return MJClient(session)


def test_real_list_jobs_returns_data(real_client: MJClient) -> None:
    try:
        page = api.list_jobs(real_client, limit=3)
    except SessionExpiredError as e:
        pytest.skip(f"session expired: {e}")
    except MJError as e:
        pytest.fail(f"MJ API error: {e} (status={e.status})")
    assert len(page.data) <= 3
    if page.data:
        first = page.data[0]
        assert first.id
        assert first.full_command
        # First image URL should be on cdn.midjourney.com
        assert first.images[0].webp.startswith("https://cdn.midjourney.com/")


def test_real_account_returns_user_id(real_client: MJClient) -> None:
    try:
        acc = api.account(real_client)
    except SessionExpiredError as e:
        pytest.skip(f"session expired: {e}")
    except MJError as e:
        pytest.fail(f"MJ API error: {e} (status={e.status})")
    # Accept any structure since /api/user-account isn't fully documented;
    # just confirm we got something back.
    assert acc.model_dump()


def test_real_queue_returns_running_and_waiting(real_client: MJClient) -> None:
    try:
        q = api.queue(real_client)
    except SessionExpiredError as e:
        pytest.skip(f"session expired: {e}")
    except MJError as e:
        pytest.fail(f"MJ API error: {e} (status={e.status})")
    assert hasattr(q, "running")
    assert hasattr(q, "waiting")
