"""Tests for midjourney_bridge.api — typed methods over a mocked transport."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from midjourney_bridge import api
from midjourney_bridge.client import MJClient
from midjourney_bridge.errors import MJError
from midjourney_bridge.models import Account, Job, JobList, QueueState
from midjourney_bridge.session import Session

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_imagine() -> dict:
    return json.loads((FIXTURES / "imagine-sample.json").read_text())


@pytest.fixture
def mock_client(fake_session: Session, fixture_imagine: dict) -> MJClient:
    """An MJClient with .get/.post replaced by canned responses keyed by path."""
    client = MJClient(fake_session)

    canned: dict[str, dict] = {
        "/api/imagine": fixture_imagine,
        "/api/imagine-update": fixture_imagine,
        "/api/user-queue": {"running": [], "waiting": []},
        "/api/user-account": {"user_id": fake_session.user_id, "plan": "Pro"},
        "/api/billing-credits": {"fast_hours_remaining": 12.5},
        "/api/styles-vector-search": {"data": [{"code": "1234", "score": 0.9}]},
        "/api/explore": {"data": [{"id": "explore-1"}]},
        "/api/explore-srefs": {"data": [{"code": "5678"}]},
    }

    def fake_get(path: str, *, params=None, referer=None) -> dict:
        return canned[path]

    client.get = MagicMock(side_effect=fake_get)  # type: ignore[method-assign]
    client.post = MagicMock(return_value={"jobId": "new-job-123"})  # type: ignore[method-assign]
    return client


def test_list_jobs_returns_typed_joblist(mock_client: MJClient) -> None:
    page = api.list_jobs(mock_client, limit=5)
    assert isinstance(page, JobList)
    assert len(page.data) == 5
    assert page.cursor == "sanitized-cursor-abc"


def test_list_jobs_passes_user_id_and_cursor(mock_client: MJClient) -> None:
    api.list_jobs(mock_client, limit=10, cursor="some-cursor")
    mock_client.get.assert_called_once()  # type: ignore[attr-defined]
    _, kwargs = mock_client.get.call_args  # type: ignore[attr-defined]
    assert kwargs["params"]["page_size"] == 10
    assert kwargs["params"]["cursor"] == "some-cursor"
    assert kwargs["params"]["user_id"] == mock_client.user_id


def test_jobs_since_uses_imagine_update(mock_client: MJClient) -> None:
    page = api.jobs_since(mock_client, checkpoint="cp-1")
    assert isinstance(page, JobList)
    args, _ = mock_client.get.call_args  # type: ignore[attr-defined]
    assert args[0] == "/api/imagine-update"


def test_queue_returns_typed(mock_client: MJClient) -> None:
    q = api.queue(mock_client)
    assert isinstance(q, QueueState)
    assert q.running == []
    assert q.waiting == []


def test_account_returns_typed(mock_client: MJClient) -> None:
    a = api.account(mock_client)
    assert isinstance(a, Account)
    assert a.plan == "Pro"


def test_find_sref_passes_query(mock_client: MJClient) -> None:
    result = api.find_sref(mock_client, "noir aesthetic")
    args, kwargs = mock_client.get.call_args  # type: ignore[attr-defined]
    assert args[0] == "/api/styles-vector-search"
    assert kwargs["params"]["prompt"] == "noir aesthetic"
    assert kwargs["params"]["_ql"] == "explore"
    assert "data" in result


def test_imagine_posts_to_submit_jobs(mock_client: MJClient) -> None:
    job_id = api.imagine(mock_client, "a red cube --ar 1:1")
    assert job_id == "new-job-123"
    mock_client.post.assert_called_once()  # type: ignore[attr-defined]
    _, kwargs = mock_client.post.call_args  # type: ignore[attr-defined]
    payload = kwargs["json"]
    assert payload["t"] == "imagine"
    assert payload["prompt"] == "a red cube --ar 1:1"
    assert payload["f"]["mode"] == "fast"
    assert "singleplayer_" in payload["channelId"]


def test_imagine_respects_mode_and_private(mock_client: MJClient) -> None:
    api.imagine(mock_client, "test", mode="relax", private=True)
    _, kwargs = mock_client.post.call_args  # type: ignore[attr-defined]
    assert kwargs["json"]["f"]["mode"] == "relax"
    assert kwargs["json"]["f"]["private"] is True


def test_upscale_posts_correct_payload(mock_client: MJClient) -> None:
    job_id = api.upscale(mock_client, "grid-job-abc", 2, variant="v8_4x_subtle")
    assert job_id == "new-job-123"
    _, kwargs = mock_client.post.call_args  # type: ignore[attr-defined]
    payload = kwargs["json"]
    assert payload["t"] == "upscale"
    assert payload["id"] == "grid-job-abc"
    assert payload["index"] == 2
    assert payload["type"] == "v8_4x_subtle"


def test_variation_posts_correct_payload(mock_client: MJClient) -> None:
    job_id = api.variation(mock_client, "grid-job-abc", 1, strong=False)
    assert job_id == "new-job-123"
    _, kwargs = mock_client.post.call_args  # type: ignore[attr-defined]
    payload = kwargs["json"]
    assert payload["t"] == "vary"
    assert payload["id"] == "grid-job-abc"
    assert payload["index"] == 1
    assert payload["strong"] is False


def test_reroll_posts_correct_payload(mock_client: MJClient) -> None:
    job_id = api.reroll(mock_client, "grid-job-abc", new_prompt="a blue cube")
    assert job_id == "new-job-123"
    _, kwargs = mock_client.post.call_args  # type: ignore[attr-defined]
    payload = kwargs["json"]
    assert payload["t"] == "reroll"
    assert payload["id"] == "grid-job-abc"
    assert payload["newPrompt"] == "a blue cube"


def test_reroll_without_prompt_sends_none(mock_client: MJClient) -> None:
    api.reroll(mock_client, "grid-job-abc")
    _, kwargs = mock_client.post.call_args  # type: ignore[attr-defined]
    assert kwargs["json"]["newPrompt"] is None


def test_submit_raises_on_missing_job_id(mock_client: MJClient) -> None:
    mock_client.post.return_value = {"unexpected": "shape"}  # type: ignore[attr-defined]
    with pytest.raises(MJError, match="missing job id"):
        api.imagine(mock_client, "test")


def test_wait_returns_job_when_found(mock_client: MJClient, fixture_imagine: dict) -> None:
    target_id = fixture_imagine["data"][0]["id"]
    job = api.wait(mock_client, target_id, timeout=1.0, poll_interval=0.01)
    assert isinstance(job, Job)
    assert job.id == target_id


def test_wait_raises_on_timeout(mock_client: MJClient) -> None:
    with pytest.raises(MJError, match="did not complete"):
        api.wait(mock_client, "nonexistent-job-id", timeout=0.05, poll_interval=0.01)


def test_video_posts_correct_payload(mock_client: MJClient) -> None:
    job_id = api.video(mock_client, "grid-job-abc", 1)
    assert job_id == "new-job-123"
    _, kwargs = mock_client.post.call_args  # type: ignore[attr-defined]
    payload = kwargs["json"]
    assert payload["t"] == "video"
    assert payload["parentJob"] == "grid-job-abc"
    assert payload["index"] == 1
    assert payload["videoType"] == "vid_1.1_i2v_480"
    assert payload["animateMode"] == "auto"
    assert payload["newPrompt"] is None


def test_video_with_prompt_and_manual_mode(mock_client: MJClient) -> None:
    api.video(mock_client, "grid-job-abc", 0, new_prompt="slowly zoom in", animate_mode="manual")
    _, kwargs = mock_client.post.call_args  # type: ignore[attr-defined]
    payload = kwargs["json"]
    assert payload["newPrompt"] == "slowly zoom in"
    assert payload["animateMode"] == "manual"


def test_video_from_url_posts_correct_payload(mock_client: MJClient) -> None:
    url = "https://cdn.midjourney.com/abc/0_0.webp"
    job_id = api.video_from_url(mock_client, url)
    assert job_id == "new-job-123"
    _, kwargs = mock_client.post.call_args  # type: ignore[attr-defined]
    payload = kwargs["json"]
    assert payload["t"] == "video"
    assert payload["imageUrl"] == url
    assert "parentJob" not in payload
