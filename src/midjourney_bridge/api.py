"""Layer 2: typed API methods.

Pure functions taking an ``MJClient``. Returns Pydantic models. No global state.
"""

from __future__ import annotations

import time
from typing import Any

from midjourney_bridge.client import MJClient
from midjourney_bridge.errors import MJError
from midjourney_bridge.models import Account, Job, JobList, QueueState

# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def list_jobs(
    client: MJClient,
    *,
    limit: int = 50,
    cursor: str | None = None,
) -> JobList:
    """Page through the user's job archive (most recent first)."""
    params: dict[str, Any] = {"user_id": client.user_id, "page_size": limit}
    if cursor:
        params["cursor"] = cursor
    raw = client.get("/api/imagine", params=params)
    return JobList.model_validate(raw)


def jobs_since(client: MJClient, *, checkpoint: str, limit: int = 1000) -> JobList:
    """Delta poll: jobs changed since the given checkpoint cursor."""
    raw = client.get(
        "/api/imagine-update",
        params={
            "user_id": client.user_id,
            "page_size": limit,
            "checkpoint": checkpoint,
        },
    )
    return JobList.model_validate(raw)


def queue(client: MJClient) -> QueueState:
    """Currently running and waiting jobs."""
    raw = client.get("/api/user-queue")
    return QueueState.model_validate(raw)


def account(client: MJClient) -> Account:
    """User account info (plan, profile). Combine with ``billing()`` for credits."""
    raw = client.get("/api/user-account")
    return Account.model_validate(raw)


def billing(client: MJClient) -> dict[str, Any]:
    """Detailed credits breakdown. Returns raw dict — schema is not stable yet."""
    return client.get("/api/billing-credits")


# ---------------------------------------------------------------------------
# Discovery (sref / explore)
# ---------------------------------------------------------------------------


def find_sref(client: MJClient, query: str, *, page: int = 0) -> dict[str, Any]:
    """Vector-search Midjourney's sref library. Returns raw dict for now."""
    return client.get(
        "/api/styles-vector-search",
        params={"prompt": query, "page": page, "_ql": "explore"},
    )


def browse_explore(
    client: MJClient,
    *,
    feed: str = "top",
    page: int = 0,
) -> dict[str, Any]:
    """Browse the community explore feed."""
    return client.get(
        "/api/explore",
        params={"page": page, "feed": feed, "_ql": "explore"},
    )


def browse_srefs(
    client: MJClient,
    *,
    feed: str = "styles_top",
    page: int = 0,
) -> dict[str, Any]:
    """Browse popular sref codes."""
    return client.get(
        "/api/explore-srefs",
        params={"page": page, "feed": feed, "_ql": "explore"},
    )


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def _envelope(
    user_id: str,
    *,
    mode: str = "fast",
    private: bool = False,
) -> dict[str, Any]:
    """Common request envelope for all submit-jobs actions."""
    return {
        "f": {"mode": mode, "private": private},
        "channelId": f"singleplayer_{user_id}",
        "metadata": {
            "isMobile": None,
            "imagePrompts": None,
            "imageReferences": None,
            "characterReferences": None,
            "depthReferences": None,
            "lightboxOpen": None,
        },
    }


def _submit(client: MJClient, payload: dict[str, Any]) -> str:
    """POST to /api/submit-jobs and return the job_id."""
    raw = client.post("/api/submit-jobs", json=payload)
    # Primary key is "jobId"; fall back to "job_id" or "id" for resilience.
    job_id = raw.get("jobId") or raw.get("job_id") or raw.get("id")
    if not isinstance(job_id, str):
        raise MJError(f"submit-jobs response missing job id: {raw!r}")
    return job_id


def imagine(
    client: MJClient,
    prompt: str,
    *,
    mode: str = "fast",
    private: bool = False,
) -> str:
    """Submit a new imagine job. Returns job_id immediately.

    All MJ flags travel inline in the prompt string: ``--ar 16:9 --v 8.1 --sref 1234``.
    Use ``wait()`` to poll until the grid is ready.
    """
    return _submit(
        client,
        {
            **_envelope(client.user_id, mode=mode, private=private),
            "t": "imagine",
            "prompt": prompt,
        },
    )


def upscale(
    client: MJClient,
    job_id: str,
    index: int,
    *,
    variant: str = "v7_2x_subtle",
) -> str:
    """Upscale one image from a grid. Returns new job_id.

    ``index`` is 0-based (0 = top-left … 3 = bottom-right).
    Common variants: ``v7_2x_subtle``, ``v7_2x_creative``, ``v8_4x_subtle``, ``v8_4x_creative``.
    """
    return _submit(
        client,
        {
            **_envelope(client.user_id),
            "t": "upscale",
            "id": job_id,
            "index": index,
            "type": variant,
        },
    )


def variation(
    client: MJClient,
    job_id: str,
    index: int,
    *,
    strong: bool = True,
) -> str:
    """Create a variation of one image from a grid. Returns new job_id.

    ``index`` is 0-based. ``strong=True`` → Strong Variation; ``False`` → Subtle.
    """
    return _submit(
        client,
        {
            **_envelope(client.user_id),
            "t": "vary",
            "id": job_id,
            "index": index,
            "strong": strong,
        },
    )


def reroll(
    client: MJClient,
    job_id: str,
    *,
    new_prompt: str | None = None,
) -> str:
    """Re-run a grid job (optionally with a prompt override). Returns new job_id."""
    return _submit(
        client,
        {
            **_envelope(client.user_id),
            "t": "reroll",
            "id": job_id,
            "newPrompt": new_prompt,
        },
    )


def video(
    client: MJClient,
    job_id: str,
    index: int,
    *,
    new_prompt: str | None = None,
    video_type: str = "vid_1.1_i2v_480",
    animate_mode: str = "auto",
) -> str:
    """Animate one image from a completed grid into a video. Returns new job_id.

    ``index`` is 0-based (0 = top-left).
    ``video_type`` controls the motion model — ``vid_1.1_i2v_480`` is the current default.
    ``animate_mode`` is ``"auto"`` (MJ picks motion) or ``"manual"`` (prompt-guided).
    """
    return _submit(
        client,
        {
            **_envelope(client.user_id),
            "t": "video",
            "parentJob": job_id,
            "index": index,
            "videoType": video_type,
            "animateMode": animate_mode,
            "newPrompt": new_prompt,
        },
    )


def video_from_url(
    client: MJClient,
    image_url: str,
    *,
    new_prompt: str | None = None,
    video_type: str = "vid_1.1_i2v_480",
    animate_mode: str = "auto",
) -> str:
    """Animate an arbitrary image URL into a video. Returns new job_id.

    Useful for animating images not in the user's MJ archive (e.g. a CDN URL
    from a different tool). Same ``video_type`` / ``animate_mode`` options as ``video()``.
    """
    return _submit(
        client,
        {
            **_envelope(client.user_id),
            "t": "video",
            "imageUrl": image_url,
            "videoType": video_type,
            "animateMode": animate_mode,
            "newPrompt": new_prompt,
        },
    )


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------


def wait(
    client: MJClient,
    job_id: str,
    *,
    timeout: float = 600.0,
    poll_interval: float = 5.0,
) -> Job:
    """Poll until a submitted job appears in the archive. Returns the completed Job.

    New jobs are returned most-recent-first by list_jobs, so checking the first
    10 entries per poll is sufficient for any freshly submitted job.

    Raises ``MJError`` on timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        page = list_jobs(client, limit=10)
        for job in page.data:
            if job.id == job_id:
                return job
        time.sleep(poll_interval)
    raise MJError(f"job {job_id} did not complete within {int(timeout)}s")
