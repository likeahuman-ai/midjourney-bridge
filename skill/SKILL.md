---
name: midjourney-bridge
description: Browse, generate, and animate Midjourney images via the user's own MJ subscription. Use when the user mentions Midjourney, MJ, past prompts, sref codes, generating images, or wants to animate/upscale/vary a result.
---

# midjourney-bridge

Drive the user's Midjourney account from Claude. Browse past work, generate new images, upscale, vary, reroll, and animate — all through MCP tools backed by the user's own subscription.

## Setup (one-time, by the user)

```bash
pip install midjourney-bridge        # or: clone + uv sync
mj cookie auto               # auto-extract from logged-in browser
mj doctor                    # verify it works
```

Add to `~/.mcp.json`:
```json
{
  "mcpServers": {
    "midjourney-bridge": { "command": "python", "args": ["-m", "midjourney_bridge.mcp"] }
  }
}
```

Restart Claude Code. Run `mj sync` first to populate the local archive.

## Tools

### Read (no API cost)
- `mj_recent(n)` — last N jobs from local archive (fast, no network)
- `mj_search_jobs(query, limit?)` — fuzzy search past prompts
- `mj_get_job(job_id)` — look up a specific job
- `mj_list_jobs(limit, cursor?)` — paginate archive (hits API)
- `mj_queue()` — currently running/waiting jobs
- `mj_account()` — plan tier, fast hours, billing
- `mj_find_sref(query, page?)` — vector search MJ's sref library
- `mj_sync_archive()` — pull new jobs into local cache

### Write (uses MJ subscription)
- `mj_imagine(prompt, mode?, private?, timeout?)` — generate images; flags inline: `--ar 16:9 --v 8.1 --sref 1234`
- `mj_upscale(job_id, index, variant?, timeout?)` — upscale one grid image (index 0-3)
- `mj_variation(job_id, index, strong?, timeout?)` — vary one grid image
- `mj_reroll(job_id, new_prompt?, timeout?)` — re-run a grid
- `mj_video(job_id, index, new_prompt?, video_type?, animate_mode?, timeout?)` — animate a grid image
- `mj_video_from_url(image_url, new_prompt?, video_type?, animate_mode?, timeout?)` — animate any image URL

All write tools block until the job completes (default timeout 600s for images, 300s for video) then return the job with image/video URLs.

## When to use

**Use proactively when the user:**
- Mentions Midjourney, MJ, "that image I made", "my recent renders"
- Asks to generate, upscale, vary, animate, or reroll
- Wants sref codes matching a vibe ("find me a noir sref")
- References a job_id or midjourney.com URL

**Don't use for:**
- Other people's MJ accounts (BYO-account only)
- Stable Diffusion, Flux, or any non-MJ tool

## Image URLs

Every job carries direct CDN URLs: `https://cdn.midjourney.com/{job_id}/0_{0..3}.webp`
Claude can render these inline.

## Repo

`github.com/likeahuman-ai/mj-bridge` (private, pre-alpha)
