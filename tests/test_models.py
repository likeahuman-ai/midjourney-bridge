"""Tests for midjourney_bridge.models against real (sanitized) MJ payloads."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from midjourney_bridge.models import GridImage, Job, JobList

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_payload() -> dict:
    return json.loads((FIXTURES / "imagine-sample.json").read_text())


def test_grid_image_urls_are_constructed() -> None:
    img = GridImage(job_id="abc-123", index=2)
    assert img.webp == "https://cdn.midjourney.com/abc-123/0_2.webp"
    assert img.png == "https://cdn.midjourney.com/abc-123/0_2.png"
    assert img.jpeg == "https://cdn.midjourney.com/abc-123/0_2.jpeg"
    assert img.url("webp") == img.webp


def test_grid_image_validates_index_range() -> None:
    with pytest.raises(ValueError):
        GridImage(job_id="x", index=4)
    with pytest.raises(ValueError):
        GridImage(job_id="x", index=-1)


def test_job_parses_real_payload(sample_payload: dict) -> None:
    raw = sample_payload["data"][0]
    job = Job.model_validate(raw)
    assert job.id
    assert job.full_command  # has a prompt
    assert job.batch_size in (1, 2, 4)
    assert job.event_type == "diffusion"


def test_job_images_derives_from_batch_size(sample_payload: dict) -> None:
    raw = sample_payload["data"][0]
    job = Job.model_validate(raw)
    assert len(job.images) == job.batch_size
    for i, img in enumerate(job.images):
        assert img.index == i
        assert img.job_id == job.id
        assert job.id in img.webp


def test_job_prompt_alias(sample_payload: dict) -> None:
    raw = sample_payload["data"][0]
    job = Job.model_validate(raw)
    assert job.prompt == job.full_command


def test_joblist_parses_full_response(sample_payload: dict) -> None:
    page = JobList.model_validate(sample_payload)
    assert len(page.data) == 5
    assert page.cursor == "sanitized-cursor-abc"
    assert page.checkpoint == "sanitized-checkpoint-xyz"
    # Every job is a typed Job
    assert all(isinstance(j, Job) for j in page.data)


def test_job_tolerates_unknown_fields() -> None:
    raw = {
        "id": "x",
        "enqueue_time": "2026-05-01T00:00:00Z",
        "job_type": "v8_unknown",
        "event_type": "diffusion",
        "batch_size": 1,
        "width": 1024,
        "height": 1024,
        "some_field_mj_added_tomorrow": "ok",
    }
    j = Job.model_validate(raw)
    # Should not raise; unknown fields preserved in dump
    dumped = j.model_dump()
    assert "some_field_mj_added_tomorrow" in dumped


def test_job_handles_missing_optional_fields() -> None:
    raw = {
        "id": "minimal",
        "enqueue_time": "2026-05-01T00:00:00Z",
        "job_type": "v8_x",
        "event_type": "diffusion",
    }
    j = Job.model_validate(raw)
    assert j.batch_size == 1  # default
    assert j.parent_id is None
    assert j.full_command is None
    assert j.prompt == ""
