# midjourney-bridge

Python client + CLI + MCP server that lets your AI tooling drive **your own** Midjourney subscription via the midjourney.com web API. No Discord. No third-party proxy. BYO account.

[![CI](https://github.com/likeahuman-ai/midjourney-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/likeahuman-ai/midjourney-bridge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: pre-alpha](https://img.shields.io/badge/status-pre--alpha-orange)](#status)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)

---

## What it does

midjourney-bridge replays the same HTTP calls the midjourney.com web UI makes. It ships in three forms that share one core library:

| Surface | How to run | Best for |
|---|---|---|
| **Python API** | `from midjourney_bridge import api` | Scripts, notebooks |
| **CLI** (`mj`) | bundled with pip install | Manual use, debugging |
| **MCP server** | `python -m midjourney_bridge.mcp` | Claude Code, Claude Desktop |

### Capabilities

| Action | CLI | MCP tool |
|---|---|---|
| List / search / browse past jobs | `mj recent`, `mj search` | `mj_recent`, `mj_search_jobs` |
| Account info + credits | `mj account` | `mj_account` |
| Live queue | `mj queue` | `mj_queue` |
| Find sref codes | — | `mj_find_sref` |
| Sync local archive | `mj sync` | `mj_sync_archive` |
| Generate images | `mj imagine "<prompt>"` | `mj_imagine` |
| Upscale | `mj upscale <job_id> <index>` | `mj_upscale` |
| Variation | `mj variation <job_id> <index>` | `mj_variation` |
| Reroll | `mj reroll <job_id>` | `mj_reroll` |
| Image-to-video | `mj video <job_id> <index>` | `mj_video` |
| Animate from URL | `mj video-url <url>` | `mj_video_from_url` |

All MJ flags travel inline in the prompt string: `--ar 16:9 --v 8.1 --sref 1234 --sw 500`

---

## Install

```bash
git clone https://github.com/likeahuman-ai/midjourney-bridge
cd mj-bridge
uv sync
```

> **PyPI release coming soon.** Once published, `pip install midjourney-bridge` will work and the MCP setup simplifies to a single command.

---

## Setup

```bash
uv run mj cookie auto   # auto-extract session from your logged-in browser
# or: uv run mj cookie set    # paste the cookie manually

uv run mj doctor        # verify the session works end-to-end
uv run mj sync          # pull your job archive locally
```

`mj cookie auto` reads the encrypted browser cookie store directly (Chrome first, then Brave, Arc, Edge, Firefox). On macOS it triggers a one-time Keychain access prompt.

---

## Usage

### CLI

```bash
mj recent 10
mj search "bioluminescent forest"
mj account

mj imagine "a red cube --ar 1:1 --v 8.1"
mj imagine "..." --mode relax --no-wait    # submit without polling

mj upscale <job_id> 0                      # upscale top-left image
mj variation <job_id> 2 --subtle
mj reroll <job_id> --prompt "new prompt"
mj video <job_id> 0                        # animate top-left image
mj video-url <cdn_url>                    # animate a CDN image URL directly
```

### Python

```python
from midjourney_bridge.client import MJClient
from midjourney_bridge.session import load
from midjourney_bridge import api

client = MJClient(load())

# Browse
page = api.list_jobs(client, limit=10)
for j in page.data:
    print(j.prompt[:60], j.images[0].webp)

# Generate
job_id = api.imagine(client, "a bioluminescent forest --ar 16:9 --v 8.1")
job = api.wait(client, job_id)
print(job.images[0].webp)
```

### MCP (Claude Code / Claude Desktop)

**1. Clone and install** (see [Install](#install) above)

**2. Authenticate**

```bash
uv run mj cookie auto   # extracts session from your logged-in browser (Keychain prompt on macOS)
uv run mj doctor        # verify end-to-end — should return your most recent job
```

**3. Register the MCP server**

Add to `~/.mcp.json` (create it if it doesn't exist), substituting your actual clone path:

```json
{
  "mcpServers": {
    "midjourney-bridge": {
      "command": "/path/to/midjourney-bridge/.venv/bin/python",
      "args": ["-m", "midjourney_bridge.mcp"]
    }
  }
}
```

The `.venv/bin/python` path ensures the right interpreter and deps regardless of your system Python. On macOS with a typical setup: `/Users/<you>/Projects/midjourney-bridge/.venv/bin/python`.

**4. Restart Claude Code** — the `mj_*` tools will be available immediately.

Alternatively, install the Claude skill from `skill/SKILL.md` into `~/.claude/skills/` for prompt-level access without the MCP server.

---

## How it works

1. You authenticate once — `mj cookie auto` extracts the session from your browser
2. All requests use [`curl_cffi`](https://github.com/lexiforest/curl_cffi) impersonating Chrome's TLS fingerprint (required — both the API and CDN enforce JA3/JA4 fingerprinting via Cloudflare)
3. Reads hit `GET /api/imagine` and related endpoints; writes go through a single `POST /api/submit-jobs` with a `t` field dispatching the action type
4. Jobs are cached locally in a JSONL archive; search runs against it with `rapidfuzz`

```
cli   mcp   skill
    archive   session
  api   models
    client (curl_cffi / Chrome 120)
        midjourney.com   cdn.midjourney.com
```

---

## Status

Pre-alpha. Tested against the live API with a real Midjourney account.

What works: all read tools, imagine, upscale, variation, reroll, video.
Not yet: describe (needs image upload capture), pan/zoom/vary-region.

---

## ⚠️ Terms of Service

This tool sends authenticated requests to midjourney.com on your behalf. **You are responsible for ensuring your usage complies with [Midjourney's ToS](https://docs.midjourney.com/hc/en-us/articles/32083055291277-Terms-of-Service).** Single-user personal use at human-level request rates is low-risk. Bulk automation or account pooling is out of scope and prohibited.

See [docs/tos-and-legal.md](docs/tos-and-legal.md).

---

## Development

```bash
uv sync --dev
./scripts/check.sh              # lint + format + types + tests
./scripts/check.sh --integration  # also hit the real API (needs mj cookie auto)
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT — see [LICENSE](LICENSE).
Built by [Like A Human](https://github.com/likeahuman-ai).
