# Contributing

Pre-alpha — the API surface is still settling. **Open an issue before writing code** so we can agree on direction first.

## Setup

```bash
git clone https://github.com/likeahuman-ai/mj-bridge
cd midjourney-bridge
uv sync --dev
```

## Quality gates

```bash
./scripts/check.sh          # lint + format + types + unit tests
./scripts/check.sh --quick  # skip mypy (faster iteration)
```

All gates must pass before a PR is mergeable. CI runs the same gates on Ubuntu + macOS × Python 3.11 + 3.12.

## Integration tests

Integration tests hit the real Midjourney API and are skipped by default:

```bash
mj cookie auto                              # configure a session first
./scripts/check.sh --integration            # then run
```

## Code style

- `ruff` for lint + format (100-char lines, double quotes)
- `mypy --strict` — no `Any` escapes without justification
- No comments explaining *what* the code does — only *why* when non-obvious
- Semantic commits: `feat(scope): subject`, `fix(scope): subject`, etc.

## What's in scope for contributions

- Bug fixes with a reproducing test
- New read endpoints (list, get, search)
- Platform support (Windows cookie extraction, new browsers)
- Docs and examples

## What's not (yet)

- Write endpoints (imagine, upscale, variation) — being designed in M2, not ready for external PRs
- Async client — on the roadmap but not scoped
- PyPI publish — after v0.1 stabilises
