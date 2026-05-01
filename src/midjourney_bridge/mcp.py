"""Layer 4 surface: MCP stdio server.

Exposes the read + write API as MCP tools so Claude (or any MCP client) can drive
the user's Midjourney account. Run with::

    python -m midjourney_bridge.mcp

or register in ``.mcp.json``::

    { "midjourney-bridge": { "command": "python", "args": ["-m", "midjourney_bridge.mcp"] } }
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from midjourney_bridge import api
from midjourney_bridge.archive import Archive
from midjourney_bridge.client import MJClient
from midjourney_bridge.errors import MJError
from midjourney_bridge.session import load

server: Server = Server("midjourney-bridge")


def _client() -> MJClient:
    """Lazy session + client -- loads cookie on first tool call."""
    return MJClient(load())


def _ok(data: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


def _err(message: str) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": message}))]


async def _write(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Submit a write action then wait for the result in a thread (non-blocking)."""
    client = _client()
    job_id = fn(client, *args, **kwargs)
    timeout = float(kwargs.pop("timeout", 600))
    job = await asyncio.to_thread(api.wait, client, job_id, timeout=timeout)
    return {"job_id": job_id, "job": job.model_dump()}


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

_READ_TOOLS = [
    Tool(
        name="mj_list_jobs",
        description="Paginate the user's Midjourney job archive (most recent first). Returns prompts + image URLs.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 50},
                "cursor": {
                    "type": "string",
                    "description": "Pagination cursor from a previous call",
                },
            },
        },
    ),
    Tool(
        name="mj_recent",
        description="Get the N most recent jobs from the local archive. Faster than mj_list_jobs (no API call).",
        inputSchema={"type": "object", "properties": {"n": {"type": "integer", "default": 10}}},
    ),
    Tool(
        name="mj_search_jobs",
        description="Fuzzy-search the user's local archive of past prompts. Returns matching jobs with image URLs.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="mj_get_job",
        description="Look up a specific job by id (from local archive cache).",
        inputSchema={
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    ),
    Tool(
        name="mj_queue",
        description="Currently running and waiting Midjourney jobs.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="mj_account",
        description="User account info: plan tier, fast hours remaining, profile.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="mj_find_sref",
        description="Vector-search Midjourney's style-reference (sref) library.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "page": {"type": "integer", "default": 0},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="mj_sync_archive",
        description="Pull new jobs from Midjourney into the local archive (incremental).",
        inputSchema={"type": "object", "properties": {}},
    ),
]

_WRITE_TOOLS = [
    Tool(
        name="mj_imagine",
        description=(
            "Submit a new Midjourney image generation job and wait for the result. "
            "Returns the completed job with 4 image URLs. "
            "All MJ flags travel inline in the prompt: --ar 16:9 --v 8.1 --sref 1234 etc."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "mode": {"type": "string", "enum": ["fast", "relax", "turbo"], "default": "fast"},
                "private": {"type": "boolean", "default": False},
                "timeout": {"type": "integer", "default": 600},
            },
            "required": ["prompt"],
        },
    ),
    Tool(
        name="mj_upscale",
        description=(
            "Upscale one image from a completed grid. "
            "index is 0-based (0=top-left, 1=top-right, 2=bottom-left, 3=bottom-right)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "index": {"type": "integer", "minimum": 0, "maximum": 3},
                "variant": {"type": "string", "default": "v7_2x_subtle"},
                "timeout": {"type": "integer", "default": 300},
            },
            "required": ["job_id", "index"],
        },
    ),
    Tool(
        name="mj_variation",
        description="Create a variation of one image from a completed grid. strong=true for Strong, false for Subtle.",
        inputSchema={
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "index": {"type": "integer", "minimum": 0, "maximum": 3},
                "strong": {"type": "boolean", "default": True},
                "timeout": {"type": "integer", "default": 600},
            },
            "required": ["job_id", "index"],
        },
    ),
    Tool(
        name="mj_reroll",
        description="Re-run a grid job with the same or an overridden prompt.",
        inputSchema={
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "new_prompt": {"type": "string"},
                "timeout": {"type": "integer", "default": 600},
            },
            "required": ["job_id"],
        },
    ),
    Tool(
        name="mj_video",
        description=(
            "Animate one image from a completed grid into a short video. "
            "index is 0-based. animate_mode: auto (MJ picks motion) or manual (prompt-guided)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "index": {"type": "integer", "minimum": 0, "maximum": 3},
                "new_prompt": {
                    "type": "string",
                    "description": "Optional motion prompt (manual mode)",
                },
                "video_type": {"type": "string", "default": "vid_1.1_i2v_480"},
                "animate_mode": {"type": "string", "enum": ["auto", "manual"], "default": "auto"},
                "timeout": {"type": "integer", "default": 300},
            },
            "required": ["job_id", "index"],
        },
    ),
    Tool(
        name="mj_video_from_url",
        description="Animate an arbitrary image URL into a short video.",
        inputSchema={
            "type": "object",
            "properties": {
                "image_url": {"type": "string"},
                "new_prompt": {"type": "string"},
                "video_type": {"type": "string", "default": "vid_1.1_i2v_480"},
                "animate_mode": {"type": "string", "enum": ["auto", "manual"], "default": "auto"},
                "timeout": {"type": "integer", "default": 300},
            },
            "required": ["image_url"],
        },
    ),
]


@server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
async def list_tools() -> list[Tool]:
    return _READ_TOOLS + _WRITE_TOOLS


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


@server.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        return await _dispatch(name, arguments)
    except MJError as e:
        return _err(f"{type(e).__name__}: {e} (status={e.status})")
    except FileNotFoundError as e:
        return _err(f"session not configured: {e} -- run `mj cookie set`")
    except Exception as e:
        return _err(f"{type(e).__name__}: {e}")


async def _dispatch(name: str, args: dict[str, Any]) -> list[TextContent]:
    # --- reads ---
    if name == "mj_list_jobs":
        page = api.list_jobs(_client(), limit=args.get("limit", 50), cursor=args.get("cursor"))
        return _ok(page.model_dump())

    if name == "mj_recent":
        jobs = list(Archive.default().iter_jobs())[: args.get("n", 10)]
        return _ok([j.model_dump() for j in jobs])

    if name == "mj_search_jobs":
        matches = Archive.default().search(args["query"], limit=args.get("limit", 20))
        return _ok([j.model_dump() for j in matches])

    if name == "mj_get_job":
        job = Archive.default().get(args["job_id"])
        return _ok(job.model_dump() if job else None)

    if name == "mj_queue":
        return _ok(api.queue(_client()).model_dump())

    if name == "mj_account":
        c = _client()
        return _ok({"account": api.account(c).model_dump(), "billing": api.billing(c)})

    if name == "mj_find_sref":
        return _ok(api.find_sref(_client(), args["query"], page=args.get("page", 0)))

    if name == "mj_sync_archive":
        return _ok({"new_jobs": Archive.default().sync(_client())})

    # --- writes ---
    if name == "mj_imagine":
        client = _client()
        job_id = api.imagine(
            client,
            args["prompt"],
            mode=args.get("mode", "fast"),
            private=args.get("private", False),
        )
        job = await asyncio.to_thread(
            api.wait, client, job_id, timeout=float(args.get("timeout", 600))
        )
        return _ok({"job_id": job_id, "job": job.model_dump()})

    if name == "mj_upscale":
        client = _client()
        job_id = api.upscale(
            client, args["job_id"], args["index"], variant=args.get("variant", "v7_2x_subtle")
        )
        job = await asyncio.to_thread(
            api.wait, client, job_id, timeout=float(args.get("timeout", 300))
        )
        return _ok({"job_id": job_id, "job": job.model_dump()})

    if name == "mj_variation":
        client = _client()
        job_id = api.variation(
            client, args["job_id"], args["index"], strong=args.get("strong", True)
        )
        job = await asyncio.to_thread(
            api.wait, client, job_id, timeout=float(args.get("timeout", 600))
        )
        return _ok({"job_id": job_id, "job": job.model_dump()})

    if name == "mj_reroll":
        client = _client()
        job_id = api.reroll(client, args["job_id"], new_prompt=args.get("new_prompt"))
        job = await asyncio.to_thread(
            api.wait, client, job_id, timeout=float(args.get("timeout", 600))
        )
        return _ok({"job_id": job_id, "job": job.model_dump()})

    if name == "mj_video":
        client = _client()
        job_id = api.video(
            client,
            args["job_id"],
            args["index"],
            new_prompt=args.get("new_prompt"),
            video_type=args.get("video_type", "vid_1.1_i2v_480"),
            animate_mode=args.get("animate_mode", "auto"),
        )
        job = await asyncio.to_thread(
            api.wait, client, job_id, timeout=float(args.get("timeout", 300))
        )
        return _ok({"job_id": job_id, "job": job.model_dump()})

    if name == "mj_video_from_url":
        client = _client()
        job_id = api.video_from_url(
            client,
            args["image_url"],
            new_prompt=args.get("new_prompt"),
            video_type=args.get("video_type", "vid_1.1_i2v_480"),
            animate_mode=args.get("animate_mode", "auto"),
        )
        job = await asyncio.to_thread(
            api.wait, client, job_id, timeout=float(args.get("timeout", 300))
        )
        return _ok({"job_id": job_id, "job": job.model_dump()})

    return _err(f"unknown tool: {name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _run() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
