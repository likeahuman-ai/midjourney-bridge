"""Tests for midjourney_bridge.archive — JSONL append + fuzzy search + sync."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from midjourney_bridge.archive import Archive
from midjourney_bridge.client import MJClient
from midjourney_bridge.models import Job
from midjourney_bridge.session import Session

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_jobs() -> list[dict]:
    return json.loads((FIXTURES / "imagine-sample.json").read_text())["data"]


@pytest.fixture
def archive(tmp_path: Path) -> Archive:
    return Archive(root=tmp_path / "midjourney-bridge-data")


def test_iter_jobs_empty(archive: Archive) -> None:
    assert list(archive.iter_jobs()) == []


def test_dump_and_iter(archive: Archive, fixture_jobs: list[dict]) -> None:
    archive.dump_raw(fixture_jobs)
    cached = list(archive.iter_jobs())
    assert len(cached) == 5
    assert all(isinstance(j, Job) for j in cached)
    # Order preserved
    assert cached[0].id == fixture_jobs[0]["id"]


def test_get_finds_by_id(archive: Archive, fixture_jobs: list[dict]) -> None:
    archive.dump_raw(fixture_jobs)
    target_id = fixture_jobs[2]["id"]
    found = archive.get(target_id)
    assert found is not None
    assert found.id == target_id


def test_get_returns_none_for_missing(archive: Archive, fixture_jobs: list[dict]) -> None:
    archive.dump_raw(fixture_jobs)
    assert archive.get("does-not-exist") is None


def test_search_finds_fuzzy_match(archive: Archive, fixture_jobs: list[dict]) -> None:
    archive.dump_raw(fixture_jobs)
    # Sample jobs include prompts about trees and nebulae
    results = archive.search("trees", limit=5)
    assert len(results) >= 1
    assert any("tree" in (j.full_command or "").lower() for j in results)


def test_search_respects_score_cutoff(archive: Archive, fixture_jobs: list[dict]) -> None:
    archive.dump_raw(fixture_jobs)
    # A query that shouldn't match anything in the fixture
    results = archive.search("xyzzy quantum spaceship", limit=5, score_cutoff=80)
    assert results == []


def test_search_empty_archive_returns_empty(archive: Archive) -> None:
    assert archive.search("anything") == []


def test_sync_full_when_no_checkpoint(
    archive: Archive,
    fixture_jobs: list[dict],
    fake_session: Session,
) -> None:
    """First sync (no checkpoint) walks list_jobs cursor pages."""
    client = MJClient(fake_session)

    page1 = {"data": fixture_jobs[:3], "cursor": "next-page", "checkpoint": "cp-final"}
    page2 = {"data": fixture_jobs[3:], "cursor": None, "checkpoint": "cp-final"}
    responses = iter([page1, page2])

    def fake_get(path: str, *, params=None, referer=None) -> dict:
        return next(responses)

    client.get = MagicMock(side_effect=fake_get)  # type: ignore[method-assign]

    n = archive.sync(client)

    assert n == 5
    assert archive.checkpoint_path.read_text() == "cp-final"
    assert len(list(archive.iter_jobs())) == 5


def test_sync_incremental_when_checkpoint_exists(
    archive: Archive,
    fixture_jobs: list[dict],
    fake_session: Session,
) -> None:
    """Subsequent syncs hit imagine-update with the saved checkpoint."""
    client = MJClient(fake_session)

    # Seed initial state
    archive.dump_raw(fixture_jobs[:3])
    archive._save_checkpoint("cp-existing")

    delta = {"data": fixture_jobs[3:], "cursor": None, "checkpoint": "cp-newer"}
    client.get = MagicMock(return_value=delta)  # type: ignore[method-assign]

    n = archive.sync(client)
    assert n == 2

    # Confirm it called imagine-update (the delta endpoint), not /api/imagine
    args, kwargs = client.get.call_args  # type: ignore[attr-defined]
    assert args[0] == "/api/imagine-update"
    assert kwargs["params"]["checkpoint"] == "cp-existing"

    # Checkpoint advanced
    assert archive.checkpoint_path.read_text() == "cp-newer"


def test_sync_dedupes_by_id(
    archive: Archive,
    fixture_jobs: list[dict],
    fake_session: Session,
) -> None:
    """Re-syncing the same jobs should not duplicate them."""
    client = MJClient(fake_session)
    archive.dump_raw(fixture_jobs)

    archive._save_checkpoint("cp-1")
    same_jobs = {"data": fixture_jobs, "cursor": None, "checkpoint": "cp-2"}
    client.get = MagicMock(return_value=same_jobs)  # type: ignore[method-assign]

    archive.sync(client)
    # Still only 5 unique
    assert len(list(archive.iter_jobs())) == 5
