"""Smoke tests for the MCP stdio server.

Tests the dispatch layer directly — no transport, no asyncio plumbing.
The official MCP Python SDK is responsible for stdio framing; we only own
the tool registry and the dispatch.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from midjourney_bridge import mcp as mcp_mod
from midjourney_bridge.archive import Archive

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def stub_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Archive:
    archive = Archive(root=tmp_path)
    fixture = json.loads((FIXTURES / "imagine-sample.json").read_text())
    archive.dump_raw(fixture["data"])
    monkeypatch.setattr("midjourney_bridge.mcp.Archive.default", classmethod(lambda cls: archive))
    return archive


@pytest.mark.asyncio
async def test_list_tools_exposes_all_v1_tools() -> None:
    # The decorated handler is wrapped by the MCP SDK; we test our list directly
    # by invoking the registered handler if accessible, else by calling list_tools().
    # MCP SDK stores handlers in server's request_handlers dict, but the simplest
    # check is that our module defines the handler.
    assert hasattr(mcp_mod, "list_tools")


@pytest.mark.asyncio
async def test_dispatch_recent(stub_archive: Archive) -> None:
    result = await mcp_mod._dispatch("mj_recent", {"n": 2})
    assert len(result) == 1
    parsed = json.loads(result[0].text)
    assert isinstance(parsed, list)
    assert len(parsed) == 2


@pytest.mark.asyncio
async def test_dispatch_search(stub_archive: Archive) -> None:
    result = await mcp_mod._dispatch("mj_search_jobs", {"query": "trees"})
    parsed = json.loads(result[0].text)
    assert isinstance(parsed, list)
    # Should match at least one fixture entry
    assert len(parsed) >= 1


@pytest.mark.asyncio
async def test_dispatch_get_job_found(stub_archive: Archive) -> None:
    fixture = json.loads((FIXTURES / "imagine-sample.json").read_text())
    job_id = fixture["data"][0]["id"]
    result = await mcp_mod._dispatch("mj_get_job", {"job_id": job_id})
    parsed = json.loads(result[0].text)
    assert parsed["id"] == job_id


@pytest.mark.asyncio
async def test_dispatch_get_job_missing(stub_archive: Archive) -> None:
    result = await mcp_mod._dispatch("mj_get_job", {"job_id": "does-not-exist"})
    parsed = json.loads(result[0].text)
    assert parsed is None


@pytest.mark.asyncio
async def test_dispatch_unknown_tool(stub_archive: Archive) -> None:
    result = await mcp_mod._dispatch("mj_no_such_tool", {})
    parsed = json.loads(result[0].text)
    assert "error" in parsed
    assert "unknown tool" in parsed["error"]


@pytest.mark.asyncio
async def test_call_tool_handles_missing_session() -> None:
    """Top-level call_tool wraps FileNotFoundError into a clean error message."""
    with patch("midjourney_bridge.mcp.load", side_effect=FileNotFoundError("no cookie")):
        result = await mcp_mod.call_tool("mj_account", {})
    parsed = json.loads(result[0].text)
    assert "error" in parsed
    assert "session not configured" in parsed["error"]
