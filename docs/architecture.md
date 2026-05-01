# Architecture

## Layer diagram

```
┌─────────────────────────────────────────────────────┐
│  Surfaces                                           │
│  cli (typer)   mcp (stdio)   skill (Claude Code)   │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│  Domain                                             │
│  session.py   archive.py (JSONL + rapidfuzz)       │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│  Typed API                                          │
│  api.py (pure functions)   models.py (Pydantic)    │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│  Transport                                          │
│  client.py — curl_cffi impersonating Chrome 120    │
│  (JA3/JA4 TLS fingerprint required by Cloudflare)  │
└────────────────────────┬────────────────────────────┘
                         │
          midjourney.com /api/*   cdn.midjourney.com
```

## Key design decisions

**curl_cffi over requests/httpx** — Cloudflare blocks standard TLS fingerprints on both the API and CDN. `curl_cffi` with `impersonate="chrome120"` passes the JA3/JA4 check without any browser binary.

**Cookie-only auth** — The web app uses a Firebase JWT (`__Host-Midjourney.AuthUserTokenV3_i`) + refresh token. We store them as-is; if the JWT expires the user re-runs `mj cookie auto`.

**`POST /api/submit-jobs` for all writes** — Midjourney dispatches imagine, upscale, variation, reroll, and video through a single endpoint with a `t` field. No separate per-action endpoints needed.

**JSONL archive over SQLite** — Append-only, grep-friendly, zero schema migrations. `rapidfuzz` handles fuzzy search over prompt text.

**Pure functions in `api.py`** — The API layer takes an explicit `MJClient` argument everywhere. No global state; easy to test, easy to use in notebooks.

## Module map

| Module | Responsibility |
|---|---|
| `client.py` | HTTP transport, error mapping, TLS impersonation |
| `session.py` | Load/save cookie, decode JWT, extract `user_id` |
| `models.py` | Pydantic models for Job, GridImage, Queue, Account |
| `api.py` | Pure functions over the MJ HTTP API |
| `archive.py` | JSONL local cache, incremental sync, fuzzy search |
| `extract.py` | Auto-extract session cookies from installed browsers |
| `cli.py` | Typer CLI (`mj` entrypoint) |
| `mcp.py` | MCP stdio server (8 read tools) |
| `errors.py` | Typed exception hierarchy |
