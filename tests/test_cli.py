"""Tests for the ``mj`` CLI."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from midjourney_bridge.archive import Archive
from midjourney_bridge.cli import app
from midjourney_bridge.session import Session

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures"


def test_help_shows_all_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in [
        "cookie",
        "doctor",
        "recent",
        "sync",
        "search",
        "account",
        "queue",
        "imagine",
        "upscale",
        "variation",
        "reroll",
    ]:
        assert cmd in result.stdout


def test_cookie_help_lists_subcommands() -> None:
    result = runner.invoke(app, ["cookie", "--help"])
    assert result.exit_code == 0
    for sub in ["auto", "set", "status"]:
        assert sub in result.stdout


def test_cookie_unknown_subcommand_errors() -> None:
    result = runner.invoke(app, ["cookie", "totally-fake-subcmd"])
    # Typer returns 2 for unknown subcommand (argparse-style)
    assert result.exit_code != 0


def test_cookie_set_writes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "config" / ".env"
    monkeypatch.setattr("midjourney_bridge.cli.config_path", lambda: target.parent)
    monkeypatch.setattr("midjourney_bridge.cli.env_path", lambda: target)
    monkeypatch.setattr("midjourney_bridge.cli.getpass.getpass", lambda _prompt: "test-cookie-value")

    result = runner.invoke(app, ["cookie", "set"], input="\n")  # blank UA
    assert result.exit_code == 0
    assert target.exists()
    assert "MJ_COOKIE=test-cookie-value" in target.read_text()


def test_cookie_status_no_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("midjourney_bridge.cli.env_path", lambda: tmp_path / "nope.env")
    result = runner.invoke(app, ["cookie", "status"])
    assert result.exit_code == 0
    assert "Nothing saved" in result.stdout


def test_cookie_auto_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """`mj cookie auto --dry-run` extracts but does not write."""
    from midjourney_bridge.extract import ExtractedSession

    fake = ExtractedSession(
        cookie="__Host-Midjourney.AuthUserTokenV3_i=fake",
        user_agent="Mozilla/5.0 fake",
        browser="chrome",
        cookie_names=("__Host-Midjourney.AuthUserTokenV3_i", "cf_clearance"),
    )
    monkeypatch.setattr("midjourney_bridge.extract.extract", lambda *a, **kw: fake)

    # Should not call _save_env in dry-run mode
    save_calls: list[tuple] = []
    monkeypatch.setattr("midjourney_bridge.cli._save_env", lambda *a, **kw: save_calls.append((a, kw)))

    result = runner.invoke(app, ["cookie", "auto", "--dry-run"])
    assert result.exit_code == 0
    assert "Found cookies in chrome" in result.stdout
    assert "dry-run" in result.stdout
    assert save_calls == []


def test_cookie_auto_writes_on_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from midjourney_bridge.extract import ExtractedSession

    target = tmp_path / "config" / ".env"
    monkeypatch.setattr("midjourney_bridge.cli.config_path", lambda: target.parent)
    monkeypatch.setattr("midjourney_bridge.cli.env_path", lambda: target)

    fake = ExtractedSession(
        cookie="__Host-Midjourney.AuthUserTokenV3_i=ok",
        user_agent="UA/1",
        browser="brave",
        cookie_names=("__Host-Midjourney.AuthUserTokenV3_i",),
    )
    monkeypatch.setattr("midjourney_bridge.extract.extract", lambda *a, **kw: fake)

    result = runner.invoke(app, ["cookie", "auto"])
    assert result.exit_code == 0
    assert target.exists()
    text = target.read_text()
    assert "MJ_COOKIE=__Host-Midjourney.AuthUserTokenV3_i=ok" in text
    assert "MJ_UA=UA/1" in text


def test_cookie_auto_extraction_failure_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    from midjourney_bridge.extract import ExtractionError

    def failing(*a, **kw):
        raise ExtractionError("nothing found anywhere")

    monkeypatch.setattr("midjourney_bridge.extract.extract", failing)
    result = runner.invoke(app, ["cookie", "auto"])
    assert result.exit_code == 1
    assert "nothing found" in (result.stdout + (result.stderr or ""))


def test_cookie_auto_unknown_browser_errors() -> None:
    result = runner.invoke(app, ["cookie", "auto", "--browser", "lynx"])
    assert result.exit_code == 1


def test_recent_empty_archive_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "midjourney_bridge.cli.Archive.default", classmethod(lambda cls: Archive(root=tmp_path))
    )
    result = runner.invoke(app, ["recent"])
    assert result.exit_code == 0
    assert "archive empty" in result.stdout


def test_recent_lists_jobs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = Archive(root=tmp_path)
    fixture = json.loads((FIXTURES / "imagine-sample.json").read_text())
    archive.dump_raw(fixture["data"])

    monkeypatch.setattr("midjourney_bridge.cli.Archive.default", classmethod(lambda cls: archive))
    result = runner.invoke(app, ["recent", "3"])
    assert result.exit_code == 0
    # Should show 3 job ids
    assert result.stdout.count("\n") >= 3


def test_search_no_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = Archive(root=tmp_path)
    fixture = json.loads((FIXTURES / "imagine-sample.json").read_text())
    archive.dump_raw(fixture["data"])

    monkeypatch.setattr("midjourney_bridge.cli.Archive.default", classmethod(lambda cls: archive))
    result = runner.invoke(app, ["search", "xyzzy-no-match-quantum"])
    assert result.exit_code == 0
    assert "no matches" in result.stdout


def test_search_finds_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = Archive(root=tmp_path)
    fixture = json.loads((FIXTURES / "imagine-sample.json").read_text())
    archive.dump_raw(fixture["data"])

    monkeypatch.setattr("midjourney_bridge.cli.Archive.default", classmethod(lambda cls: archive))
    result = runner.invoke(app, ["search", "trees"])
    assert result.exit_code == 0
    assert "no matches" not in result.stdout


def test_doctor_no_cookie_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_missing(env_file=None) -> Session:
        raise FileNotFoundError("No MJ_COOKIE found")

    monkeypatch.setattr("midjourney_bridge.cli.load", raise_missing)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1


def test_doctor_happy_path(fake_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("midjourney_bridge.cli.load", lambda env_file=None: fake_session)

    fake_page = type(
        "P",
        (),
        {"data": [type("J", (), {"id": "j1", "prompt": "test prompt"})()]},
    )()
    with patch("midjourney_bridge.cli.api.list_jobs", return_value=fake_page):
        result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "API ok" in result.stdout
    assert "j1" in result.stdout


# ---------------------------------------------------------------------------
# Write commands
# ---------------------------------------------------------------------------


def _fake_job(job_id: str = "done-job-abc") -> object:
    from midjourney_bridge.models import Job

    return Job(
        id=job_id,
        enqueue_time="2025-01-01T00:00:00Z",
        full_command="a red cube --ar 1:1",
        job_type="v7_raw_diffusion",
        event_type="diffusion",
        batch_size=4,
        width=1024,
        height=1024,
    )


def test_imagine_no_wait(fake_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("midjourney_bridge.cli.load", lambda env_file=None: fake_session)
    with patch("midjourney_bridge.cli.api.imagine", return_value="new-job-123"):
        result = runner.invoke(app, ["imagine", "a red cube", "--no-wait"])
    assert result.exit_code == 0
    assert "new-job-123" in result.stdout


def test_imagine_with_wait(fake_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("midjourney_bridge.cli.load", lambda env_file=None: fake_session)
    job = _fake_job("done-job-abc")
    with (
        patch("midjourney_bridge.cli.api.imagine", return_value="done-job-abc"),
        patch("midjourney_bridge.cli.api.wait", return_value=job),
    ):
        result = runner.invoke(app, ["imagine", "a red cube"])
    assert result.exit_code == 0
    assert "done-job-abc" in result.stdout
    assert "cdn.midjourney.com" in result.stdout


def test_imagine_invalid_mode(fake_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("midjourney_bridge.cli.load", lambda env_file=None: fake_session)
    result = runner.invoke(app, ["imagine", "test", "--mode", "warp"])
    assert result.exit_code == 1


def test_upscale_no_wait(fake_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("midjourney_bridge.cli.load", lambda env_file=None: fake_session)
    with patch("midjourney_bridge.cli.api.upscale", return_value="upscale-job-1"):
        result = runner.invoke(app, ["upscale", "grid-abc", "0", "--no-wait"])
    assert result.exit_code == 0
    assert "upscale-job-1" in result.stdout


def test_upscale_bad_index(fake_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("midjourney_bridge.cli.load", lambda env_file=None: fake_session)
    result = runner.invoke(app, ["upscale", "grid-abc", "9", "--no-wait"])
    assert result.exit_code == 1


def test_variation_no_wait(fake_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("midjourney_bridge.cli.load", lambda env_file=None: fake_session)
    with patch("midjourney_bridge.cli.api.variation", return_value="var-job-1"):
        result = runner.invoke(app, ["variation", "grid-abc", "2", "--no-wait"])
    assert result.exit_code == 0
    assert "var-job-1" in result.stdout


def test_variation_subtle_flag(fake_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("midjourney_bridge.cli.load", lambda env_file=None: fake_session)
    calls: list[dict] = []

    def capture(client, job_id, index, *, strong=True) -> str:
        calls.append({"strong": strong})
        return "var-job-2"

    with patch("midjourney_bridge.cli.api.variation", side_effect=capture):
        runner.invoke(app, ["variation", "grid-abc", "1", "--subtle", "--no-wait"])

    assert calls[0]["strong"] is False


def test_reroll_no_wait(fake_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("midjourney_bridge.cli.load", lambda env_file=None: fake_session)
    with patch("midjourney_bridge.cli.api.reroll", return_value="reroll-job-1"):
        result = runner.invoke(app, ["reroll", "grid-abc", "--no-wait"])
    assert result.exit_code == 0
    assert "reroll-job-1" in result.stdout


def test_reroll_with_prompt(fake_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("midjourney_bridge.cli.load", lambda env_file=None: fake_session)
    calls: list[dict] = []

    def capture(client, job_id, *, new_prompt=None) -> str:
        calls.append({"new_prompt": new_prompt})
        return "reroll-job-2"

    with patch("midjourney_bridge.cli.api.reroll", side_effect=capture):
        runner.invoke(app, ["reroll", "grid-abc", "--prompt", "a blue cube", "--no-wait"])

    assert calls[0]["new_prompt"] == "a blue cube"
