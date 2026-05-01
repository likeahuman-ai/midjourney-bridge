"""Write commands for the ``mj`` CLI: imagine, upscale, variation, reroll.

Registered onto the shared Typer app via ``_register_write_commands(app)``
called at the bottom of ``cli.py``. Kept in a separate module so cli.py
stays under the 300-line file-size guard.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

import typer

from midjourney_bridge import api
from midjourney_bridge.client import MJClient
from midjourney_bridge.errors import MJError


def _register_write_commands(app: typer.Typer, client_factory: Callable[[], MJClient]) -> None:
    """Attach write commands to ``app``. Called once at import time from cli.py."""

    @app.command()
    def imagine(
        prompt: Annotated[
            str,
            typer.Argument(help="Prompt text — include inline flags: --ar 16:9 --v 8.1"),
        ],
        mode: Annotated[
            str,
            typer.Option("--mode", "-m", help="Generation mode: fast, relax, turbo"),
        ] = "fast",
        private: Annotated[
            bool,
            typer.Option("--private/--no-private", help="Private job"),
        ] = False,
        no_wait: Annotated[
            bool,
            typer.Option("--no-wait", help="Return job_id immediately without polling"),
        ] = False,
        timeout: Annotated[int, typer.Option("--timeout", help="Max seconds to wait")] = 600,
    ) -> None:
        """Submit a new Midjourney image generation job."""
        if mode not in ("fast", "relax", "turbo"):
            typer.secho(
                f"✗ invalid mode '{mode}' - use fast, relax, or turbo",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)

        client = client_factory()
        try:
            job_id = api.imagine(client, prompt, mode=mode, private=private)
        except MJError as e:
            typer.secho(f"✗ submit failed: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from e

        typer.secho(f"✓ submitted  {job_id}", fg=typer.colors.GREEN)

        if no_wait:
            typer.echo("(use `mj recent 1` after completion to see the result)")
            return

        typer.echo(f"  polling every 5s (timeout {timeout}s)...")
        try:
            job = api.wait(client, job_id, timeout=float(timeout))
        except MJError as e:
            typer.secho(f"✗ {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from e

        typer.secho(f"✓ done  {job.id}", fg=typer.colors.GREEN)
        for img in job.images:
            typer.echo(f"  {img.webp}")

    @app.command()
    def upscale(
        job_id: Annotated[str, typer.Argument(help="Job ID of the source grid")],
        index: Annotated[int, typer.Argument(help="Image index 0-3 (0=top-left)")],
        variant: Annotated[
            str,
            typer.Option(
                "--variant",
                "-v",
                help="Upscale variant: v7_2x_subtle, v7_2x_creative, v8_4x_subtle, v8_4x_creative",
            ),
        ] = "v7_2x_subtle",
        no_wait: Annotated[bool, typer.Option("--no-wait")] = False,
        timeout: Annotated[int, typer.Option("--timeout")] = 300,
    ) -> None:
        """Upscale one image from a grid."""
        if index not in range(4):
            typer.secho("✗ index must be 0-3", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        client = client_factory()
        try:
            new_id = api.upscale(client, job_id, index, variant=variant)
        except MJError as e:
            typer.secho(f"✗ {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from e

        typer.secho(f"✓ submitted  {new_id}", fg=typer.colors.GREEN)
        if no_wait:
            return

        typer.echo(f"  polling every 5s (timeout {timeout}s)...")
        try:
            job = api.wait(client, new_id, timeout=float(timeout))
        except MJError as e:
            typer.secho(f"✗ {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from e

        typer.secho(f"✓ done  {job.id}", fg=typer.colors.GREEN)
        typer.echo(f"  {job.images[0].webp}")

    @app.command(name="video-url")
    def video_url(
        image_url: Annotated[str, typer.Argument(help="Direct CDN image URL to animate")],
        prompt: Annotated[
            str | None,
            typer.Option("--prompt", "-p", help="Optional motion prompt (manual mode)"),
        ] = None,
        manual: Annotated[
            bool,
            typer.Option("--manual/--auto", help="Manual (prompt-guided) or auto motion"),
        ] = False,
        video_type: Annotated[
            str,
            typer.Option("--type", help="Video model, e.g. vid_1.1_i2v_480"),
        ] = "vid_1.1_i2v_480",
        no_wait: Annotated[bool, typer.Option("--no-wait")] = False,
        timeout: Annotated[int, typer.Option("--timeout")] = 300,
    ) -> None:
        """Animate a CDN image URL directly into a video."""
        client = client_factory()
        try:
            new_id = api.video_from_url(
                client,
                image_url,
                new_prompt=prompt,
                video_type=video_type,
                animate_mode="manual" if manual else "auto",
            )
        except MJError as e:
            typer.secho(f"✗ {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from e

        typer.secho(f"✓ submitted  {new_id}", fg=typer.colors.GREEN)
        if no_wait:
            return

        typer.echo(f"  polling every 5s (timeout {timeout}s)...")
        try:
            job = api.wait(client, new_id, timeout=float(timeout))
        except MJError as e:
            typer.secho(f"✗ {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from e

        typer.secho(f"✓ done  {job.id}", fg=typer.colors.GREEN)
        typer.echo(f"  {job.images[0].webp}")

    @app.command()
    def variation(
        job_id: Annotated[str, typer.Argument(help="Job ID of the source grid")],
        index: Annotated[int, typer.Argument(help="Image index 0-3")],
        subtle: Annotated[
            bool,
            typer.Option("--subtle/--strong", help="Subtle or Strong variation"),
        ] = False,
        no_wait: Annotated[bool, typer.Option("--no-wait")] = False,
        timeout: Annotated[int, typer.Option("--timeout")] = 600,
    ) -> None:
        """Create a variation of one image from a grid."""
        if index not in range(4):
            typer.secho("✗ index must be 0-3", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        client = client_factory()
        try:
            new_id = api.variation(client, job_id, index, strong=not subtle)
        except MJError as e:
            typer.secho(f"✗ {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from e

        typer.secho(f"✓ submitted  {new_id}", fg=typer.colors.GREEN)
        if no_wait:
            return

        typer.echo(f"  polling every 5s (timeout {timeout}s)...")
        try:
            job = api.wait(client, new_id, timeout=float(timeout))
        except MJError as e:
            typer.secho(f"✗ {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from e

        typer.secho(f"✓ done  {job.id}", fg=typer.colors.GREEN)
        for img in job.images:
            typer.echo(f"  {img.webp}")

    @app.command()
    def reroll(
        job_id: Annotated[str, typer.Argument(help="Job ID to re-run")],
        prompt: Annotated[
            str | None,
            typer.Option("--prompt", "-p", help="Override prompt (omit to reuse original)"),
        ] = None,
        no_wait: Annotated[bool, typer.Option("--no-wait")] = False,
        timeout: Annotated[int, typer.Option("--timeout")] = 600,
    ) -> None:
        """Re-run a grid job (optionally with a new prompt)."""
        client = client_factory()
        try:
            new_id = api.reroll(client, job_id, new_prompt=prompt)
        except MJError as e:
            typer.secho(f"✗ {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from e

        typer.secho(f"✓ submitted  {new_id}", fg=typer.colors.GREEN)
        if no_wait:
            return

        typer.echo(f"  polling every 5s (timeout {timeout}s)...")
        try:
            job = api.wait(client, new_id, timeout=float(timeout))
        except MJError as e:
            typer.secho(f"✗ {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from e

        typer.secho(f"✓ done  {job.id}", fg=typer.colors.GREEN)
        for img in job.images:
            typer.echo(f"  {img.webp}")

    @app.command()
    def video(
        job_id: Annotated[str, typer.Argument(help="Grid job ID to animate")],
        index: Annotated[int, typer.Argument(help="Image index 0-3")],
        prompt: Annotated[
            str | None,
            typer.Option("--prompt", "-p", help="Optional motion prompt (manual mode)"),
        ] = None,
        manual: Annotated[
            bool,
            typer.Option("--manual/--auto", help="Manual (prompt-guided) or auto motion"),
        ] = False,
        video_type: Annotated[
            str,
            typer.Option("--type", help="Video model, e.g. vid_1.1_i2v_480"),
        ] = "vid_1.1_i2v_480",
        no_wait: Annotated[bool, typer.Option("--no-wait")] = False,
        timeout: Annotated[int, typer.Option("--timeout")] = 300,
    ) -> None:
        """Animate one image from a grid into a video."""
        if index not in range(4):
            typer.secho("✗ index must be 0-3", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        client = client_factory()
        try:
            new_id = api.video(
                client,
                job_id,
                index,
                new_prompt=prompt,
                video_type=video_type,
                animate_mode="manual" if manual else "auto",
            )
        except MJError as e:
            typer.secho(f"✗ {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from e

        typer.secho(f"✓ submitted  {new_id}", fg=typer.colors.GREEN)
        if no_wait:
            return

        typer.echo(f"  polling every 5s (timeout {timeout}s)...")
        try:
            job = api.wait(client, new_id, timeout=float(timeout))
        except MJError as e:
            typer.secho(f"✗ {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from e

        typer.secho(f"✓ done  {job.id}", fg=typer.colors.GREEN)
        typer.echo(f"  {job.images[0].webp}")
