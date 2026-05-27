"""Typer CLI for Pinser."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pinser.app.config.settings import load_settings

DEFAULT_WORKSPACE = Path.cwd()

app = typer.Typer(
    add_completion=False,
    help="Pinser command-line interface.",
    no_args_is_help=False,
)


@app.command()
def main(
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
            help="Workspace root used to initialize Pinser.",
        ),
    ] = DEFAULT_WORKSPACE,
) -> None:
    """Start the minimal Pinser CLI bootstrap."""

    settings = load_settings(workspace)
    typer.echo(
        "Pinser is initialized and ready to grow. "
        f"workspace={settings.paths.workspace_root} "
        f"state_dir={settings.paths.state_dir}"
    )


if __name__ == "__main__":
    app()
