"""Pydantic models for Midjourney's web/JSON API responses.

Models use ``extra="allow"`` so MJ adding fields doesn't break us — we surface
known fields as typed attributes and keep unknowns accessible via ``model_dump()``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

CDN_BASE = "https://cdn.midjourney.com"

ImageFormat = Literal["webp", "png", "jpeg"]


class _Tolerant(BaseModel):
    """Base model that tolerates unknown fields and uses immutable instances."""

    model_config = ConfigDict(extra="allow", frozen=True)


class GridImage(_Tolerant):
    """One image in a Midjourney grid. URL is constructed from job_id + index.

    The MJ CDN serves the same image as webp / png / jpeg from predictable paths.
    No auth required; only TLS fingerprint enforced (handled by transport layer).
    """

    job_id: str
    index: int = Field(ge=0, le=3)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def webp(self) -> str:
        return f"{CDN_BASE}/{self.job_id}/0_{self.index}.webp"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def png(self) -> str:
        return f"{CDN_BASE}/{self.job_id}/0_{self.index}.png"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def jpeg(self) -> str:
        return f"{CDN_BASE}/{self.job_id}/0_{self.index}.jpeg"

    def url(self, fmt: ImageFormat = "webp") -> str:
        """Return the CDN URL for a given format."""
        return f"{CDN_BASE}/{self.job_id}/0_{self.index}.{fmt}"


class Job(_Tolerant):
    """A Midjourney job: imagine, upscale, variation, video, etc.

    Field names mirror the wire format. Use ``.images`` for derived image URLs.
    """

    id: str
    enqueue_time: str
    full_command: str | None = None
    job_type: str  # e.g. "v8-1_hd_diffusion", "v7_raw_diffusion"
    event_type: str  # e.g. "diffusion"
    batch_size: int = 1
    width: int = 0
    height: int = 0
    parent_id: str | None = None
    parent_grid: int | None = None
    rating: Any = None
    published: bool = False
    shown: bool = True
    user_hidden: bool = False
    template: str | None = None
    personalization_codes: list[dict[str, Any]] = Field(default_factory=list)
    video_segments: list[Any] | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def images(self) -> list[GridImage]:
        """The N images in this job's grid (N = batch_size)."""
        return [GridImage(job_id=self.id, index=i) for i in range(self.batch_size)]

    @property
    def prompt(self) -> str:
        """Convenience alias for full_command (which is what the MJ wire format calls it)."""
        return self.full_command or ""


class JobList(_Tolerant):
    """Paginated job list response from /api/imagine."""

    data: list[Job]
    cursor: str | None = None
    checkpoint: str | None = None


class QueueState(_Tolerant):
    """Currently running and waiting jobs from /api/user-queue."""

    running: list[dict[str, Any]] = Field(default_factory=list)
    waiting: list[dict[str, Any]] = Field(default_factory=list)


class Account(_Tolerant):
    """User account info — combines /api/user-account and /api/billing-credits.

    Wire format is poorly documented; we tolerate any shape and surface known fields
    when present. Use ``model_dump()`` to see everything.
    """

    user_id: str | None = None
    plan: str | None = None
    fast_hours_remaining: float | None = None
    relax_remaining: float | None = None


class SrefHit(_Tolerant):
    """A single result from /api/styles-vector-search."""

    code: str | None = None
    score: float | None = None
    thumbnail: str | None = None
