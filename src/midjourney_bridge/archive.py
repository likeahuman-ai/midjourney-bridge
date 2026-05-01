"""Layer 3: local JSONL archive cache + fuzzy search.

Append-only line-delimited JSON. One job per line, keyed by ``id``. Supports
incremental sync via the ``checkpoint`` cursor from the imagine-update endpoint.

For personal-scale archives (~10k jobs) JSONL + in-memory rapidfuzz is plenty —
no SQLite, no FTS index, no rebuild step.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir
from rapidfuzz import fuzz, process

from midjourney_bridge import api
from midjourney_bridge.client import MJClient
from midjourney_bridge.models import Job

DATA_APP = "mj-bridge"  # stable storage name — never changes with package renames
ARCHIVE_FILENAME = "archive.jsonl"
CHECKPOINT_FILENAME = "checkpoint"


def data_path() -> Path:
    """Return the OS-native data directory for midjourney-bridge."""
    return Path(user_data_dir(DATA_APP))


@dataclass(frozen=True)
class Archive:
    """Local JSONL job archive. Pass a custom path for tests; default uses platformdirs."""

    root: Path

    @classmethod
    def default(cls) -> Archive:
        return cls(root=data_path())

    @property
    def jsonl_path(self) -> Path:
        return self.root / ARCHIVE_FILENAME

    @property
    def checkpoint_path(self) -> Path:
        return self.root / CHECKPOINT_FILENAME

    def _ensure_dir(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    # -- Read --------------------------------------------------------------

    def iter_jobs(self) -> Iterator[Job]:
        """Stream every cached job from disk."""
        if not self.jsonl_path.exists():
            return
        with self.jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield Job.model_validate_json(line)

    def get(self, job_id: str) -> Job | None:
        """Find a job by id (linear scan; fine for personal scale)."""
        for j in self.iter_jobs():
            if j.id == job_id:
                return j
        return None

    def search(self, query: str, *, limit: int = 50, score_cutoff: int = 50) -> list[Job]:
        """Fuzzy-match ``query`` against full_command. Highest scores first."""
        jobs = list(self.iter_jobs())
        if not jobs:
            return []
        # Build a (prompt, idx) corpus
        prompts = [(j.prompt, i) for i, j in enumerate(jobs)]
        results = process.extract(
            query,
            [p for p, _ in prompts],
            scorer=fuzz.WRatio,
            limit=limit,
            score_cutoff=score_cutoff,
        )
        return [jobs[idx] for _, _score, idx in results]

    # -- Write -------------------------------------------------------------

    def sync(self, client: MJClient, *, page_size: int = 1000) -> int:
        """Pull jobs since last checkpoint and append to JSONL.

        Returns the number of new jobs written. If no checkpoint exists yet, falls
        back to full pagination via ``api.list_jobs``.
        """
        self._ensure_dir()
        checkpoint = self._load_checkpoint()

        if checkpoint:
            page = api.jobs_since(client, checkpoint=checkpoint, limit=page_size)
            new_jobs = page.data
            new_checkpoint = page.checkpoint
        else:
            new_jobs, new_checkpoint = self._full_sync(client, page_size=page_size)

        if new_jobs:
            self._append_jobs(new_jobs)
        if new_checkpoint:
            self._save_checkpoint(new_checkpoint)
        return len(new_jobs)

    def _full_sync(self, client: MJClient, *, page_size: int) -> tuple[list[Job], str | None]:
        """Initial full archive pull. Walks the cursor until exhausted."""
        all_jobs: list[Job] = []
        cursor: str | None = None
        last_checkpoint: str | None = None
        while True:
            page = api.list_jobs(client, limit=page_size, cursor=cursor)
            all_jobs.extend(page.data)
            last_checkpoint = page.checkpoint or last_checkpoint
            if not page.cursor or not page.data:
                break
            cursor = page.cursor
        return all_jobs, last_checkpoint

    def _append_jobs(self, jobs: list[Job]) -> None:
        existing_ids = {j.id for j in self.iter_jobs()}
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            for job in jobs:
                if job.id in existing_ids:
                    continue
                f.write(job.model_dump_json() + "\n")

    def _load_checkpoint(self) -> str | None:
        if not self.checkpoint_path.exists():
            return None
        return self.checkpoint_path.read_text(encoding="utf-8").strip() or None

    def _save_checkpoint(self, checkpoint: str) -> None:
        self.checkpoint_path.write_text(checkpoint, encoding="utf-8")

    def dump_raw(self, raw_jobs: list[dict[str, Any]]) -> None:
        """Helper for tests/imports: append a list of raw dicts as JSONL."""
        self._ensure_dir()
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            for raw in raw_jobs:
                f.write(json.dumps(raw, separators=(",", ":")) + "\n")
