"""Layer 4 surface: ``mj`` CLI built on Typer.

Wraps the Layer 2 API + Layer 3 archive. Thin -- all real logic lives below.
Write commands (imagine, upscale, variation, reroll) live in _cli_writes.py.
"""

from __future__ import annotations

import getpass
import json
import os
import sys
import time
from datetime import UTC, datetime
from typing import Annotated

import typer

from midjourney_bridge import __version__, api
from midjourney_bridge.archive import Archive
from midjourney_bridge.client import MJClient
from midjourney_bridge.errors import MJError
from midjourney_bridge.session import config_path, env_path, load


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"midjourney-bridge {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="mj",
    help="Drive your own Midjourney subscription from the command line.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _main(
    version: Annotated[
        bool,
        typer.Option(
            "--version", "-V", callback=_version_callback, is_eager=True, help="Show version"
        ),
    ] = False,
) -> None:
    pass


cookie_app = typer.Typer(
    help="Manage the stored MJ session cookie.",
    no_args_is_help=True,
)
app.add_typer(cookie_app, name="cookie")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client() -> MJClient:
    """Load session and return a configured client. Exits on missing config."""
    try:
        session = load()
    except (FileNotFoundError, ValueError) as e:
        typer.secho(f"✗ {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e
    return MJClient(session)


def _redact(s: str, keep: int = 8) -> str:
    return "***" if len(s) <= keep * 2 else f"{s[:keep]}...{s[-keep:]} ({len(s)} chars)"


def _save_env(cookie: str, user_agent: str | None) -> None:
    """Write cookie + optional UA to the config .env (chmod 0600)."""
    config_path().mkdir(parents=True, exist_ok=True)
    path = env_path()
    lines = [f"MJ_COOKIE={cookie}"]
    if user_agent:
        lines.append(f"MJ_UA={user_agent}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


# ---------------------------------------------------------------------------
# `mj cookie *` subcommands
# ---------------------------------------------------------------------------


@cookie_app.command("auto")
def cookie_auto(
    browser: Annotated[
        str | None,
        typer.Option("--browser", "-b", help="Force a browser. Default: try all in order."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be saved without writing."),
    ] = False,
) -> None:
    """Auto-extract the MJ session from your logged-in browser."""
    from midjourney_bridge.extract import ExtractionError, extract, supported_browsers

    if browser and browser not in supported_browsers():
        typer.secho(
            f"✗ unknown browser: {browser!r}. Supported: {', '.join(supported_browsers())}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(f"Extracting MJ session from {browser or 'browsers (auto)'}...")
    try:
        session = extract(browser)
    except ExtractionError as e:
        typer.secho(f"\n✗ {e}", fg=typer.colors.RED, err=True)
        typer.echo("\nFallback: paste manually with `mj cookie set`")
        raise typer.Exit(code=1) from e

    typer.secho(f"✓ Found cookies in {session.browser}", fg=typer.colors.GREEN)
    typer.echo(f"  cookies: {', '.join(session.cookie_names)}")
    typer.echo(f"  ua:      {session.user_agent}")

    if dry_run:
        typer.secho(f"\n(dry-run -- would save to {env_path()})", fg=typer.colors.YELLOW)
        return

    _save_env(session.cookie, session.user_agent)
    typer.secho(f"\n✓ saved -> {env_path()} (chmod 0600)", fg=typer.colors.GREEN)
    typer.echo("\nNext: `mj doctor` to verify the session works against MJ.")


@cookie_app.command("set")
def cookie_set() -> None:
    """Paste a session cookie manually (interactive, hidden input)."""
    typer.echo("Paste the full cookie value from devtools (input is hidden):")
    cookie_str = getpass.getpass("> ").strip()
    if not cookie_str:
        typer.secho("✗ empty input -- nothing saved", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo("Optional: paste your Chrome User-Agent (leave blank for default):")
    ua = input("> ").strip() or None
    _save_env(cookie_str, ua)
    typer.secho(f"✓ saved -> {env_path()} (chmod 0600)", fg=typer.colors.GREEN)


@cookie_app.command("status")
def cookie_status() -> None:
    """Show what is currently saved + token freshness."""
    typer.echo(f"config: {env_path()}")
    typer.echo(f"exists: {env_path().exists()}")
    if not env_path().exists():
        typer.secho(
            "\nNothing saved. Run `mj cookie auto` or `mj cookie set`.", fg=typer.colors.YELLOW
        )
        raise typer.Exit(code=0)

    try:
        session = load()
    except (FileNotFoundError, ValueError) as e:
        typer.secho(f"✗ load failed: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e

    typer.echo(f"user_id: {session.user_id}")
    typer.echo(f"cookie:  {_redact(session.cookie)}")
    typer.echo(f"ua:      {session.user_agent}")

    try:
        from midjourney_bridge.session import _decode_jwt_payload

        cookies = dict(kv.split("=", 1) for kv in session.cookie.split("; ") if "=" in kv)
        jwt = cookies.get("__Host-Midjourney.AuthUserTokenV3_i")
        if jwt:
            payload = _decode_jwt_payload(jwt)
            exp = payload.get("exp")
            if isinstance(exp, int):
                now = int(time.time())
                delta = exp - now
                exp_dt = datetime.fromtimestamp(exp, tz=UTC)
                if delta < 0:
                    typer.secho(
                        f"jwt:     EXPIRED {-delta // 60}m ago at {exp_dt:%Y-%m-%d %H:%M UTC}",
                        fg=typer.colors.RED,
                    )
                    typer.echo("(refresh with `mj cookie auto` or re-paste)")
                else:
                    typer.echo(
                        f"jwt:     valid for {delta // 60}m (expires {exp_dt:%Y-%m-%d %H:%M UTC})"
                    )
    except Exception as e:
        typer.echo(f"jwt:     (could not decode: {e})")


# ---------------------------------------------------------------------------
# Read commands
# ---------------------------------------------------------------------------


@app.command()
def doctor() -> None:
    """Validate the session and ping MJ end-to-end."""
    typer.echo(f"config: {env_path()}")
    typer.echo(f"exists: {env_path().exists()}")

    try:
        session = load()
    except (FileNotFoundError, ValueError) as e:
        typer.secho(f"✗ session: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e

    typer.echo(f"user_id: {session.user_id}")
    typer.echo(f"cookie:  {_redact(session.cookie)}")
    typer.echo(f"ua:      {session.user_agent}")

    client = MJClient(session)
    try:
        page = api.list_jobs(client, limit=1)
    except MJError as e:
        typer.secho(
            f"\n✗ API call failed: {e} (status={e.status})",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from e

    typer.secho(f"\n✓ API ok -- {len(page.data)} job(s) returned", fg=typer.colors.GREEN)
    if page.data:
        first = page.data[0]
        typer.echo(f"  most recent: {first.id}")
        typer.echo(f"  prompt:      {first.prompt[:80]!r}...")


@app.command()
def recent(n: Annotated[int, typer.Argument(help="How many recent jobs")] = 10) -> None:
    """Print the N most recent jobs from the local archive."""
    archive = Archive.default()
    jobs = list(archive.iter_jobs())[:n]
    if not jobs:
        typer.echo("(archive empty -- run `mj sync` first)")
        return
    for j in jobs:
        prompt = (j.prompt or "")[:70].replace("\n", " ")
        typer.echo(f"{j.id}  [{j.job_type}]  {prompt!r}")


@app.command()
def sync() -> None:
    """Pull jobs from MJ into the local archive (incremental after first run)."""
    client = _client()
    archive = Archive.default()
    n = archive.sync(client)
    typer.secho(f"✓ synced {n} new job(s) -> {archive.jsonl_path}", fg=typer.colors.GREEN)


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 20,
) -> None:
    """Fuzzy-search the local archive prompts."""
    archive = Archive.default()
    matches = archive.search(query, limit=limit)
    if not matches:
        typer.echo("(no matches)")
        return
    for j in matches:
        prompt = (j.prompt or "")[:70].replace("\n", " ")
        typer.echo(f"{j.id}  {prompt!r}")


@app.command()
def account() -> None:
    """Print account info: plan, profile, credits."""
    client = _client()
    acc = api.account(client)
    bill = api.billing(client)
    typer.echo(json.dumps({"account": acc.model_dump(), "billing": bill}, indent=2))


@app.command()
def queue() -> None:
    """Print currently running and waiting jobs."""
    client = _client()
    q = api.queue(client)
    typer.echo(json.dumps(q.model_dump(), indent=2))


# Register write commands (imagine, upscale, variation, reroll).
from midjourney_bridge._cli_writes import _register_write_commands  # noqa: E402

_register_write_commands(app, _client)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for ``python -m midjourney_bridge.cli``."""
    try:
        app()
    except KeyboardInterrupt:
        typer.echo("\n(interrupted)", err=True)
        sys.exit(130)


if __name__ == "__main__":
    main()
