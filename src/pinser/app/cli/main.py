"""Typer CLI for Pinser."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from pinser.app.config.settings import load_settings
from pinser.runtime.engine import Runtime
from pinser.runtime.events.models import (
    AssistantMessageEvent,
    Event,
    PermissionRequiredEvent,
    ProgressEvent,
    ToolCompletedEvent,
    ToolDeniedEvent,
    ToolFailedEvent,
    ToolStartedEvent,
    TurnCancelledEvent,
    TurnCompletedEvent,
    TurnStartedEvent,
    UserMessageEvent,
)

DEFAULT_WORKSPACE = Path.cwd()

app = typer.Typer(
    name="pinser",
    add_completion=False,
    help="Pinser command-line interface.",
    no_args_is_help=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
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
    typer.echo("Pinser initialized.")
    typer.echo(f"workspace={settings.paths.workspace_root}")
    typer.echo(f"state_dir={settings.paths.state_dir}")


@app.command("run-turn")
def run_turn_command(
    message: str,
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
    """Run one minimal runtime turn and print streamed events."""

    load_settings(workspace)
    runtime = Runtime.create()

    events = asyncio.run(runtime.run_turn(message))
    for event in events:
        typer.echo(_render_event(event))


def _render_event(event: Event) -> str:
    if isinstance(event, TurnStartedEvent):
        return f"turn-started turn_id={event.turn_id} user={event.user_message}"
    if isinstance(event, UserMessageEvent):
        return f"user: {event.message}"
    if isinstance(event, ProgressEvent):
        return f"Progress: {event.stage}"
    if isinstance(event, ToolStartedEvent):
        return f"tool-started tool={event.tool_name} summary={event.summary}"
    if isinstance(event, ToolCompletedEvent):
        return f"tool-completed tool={event.tool_name} summary={event.summary}"
    if isinstance(event, PermissionRequiredEvent):
        return f"Permission required: {event.summary}"
    if isinstance(event, ToolDeniedEvent):
        return f"Denied: {event.reason}"
    if isinstance(event, ToolFailedEvent):
        return f"Error: {event.reason}"
    if isinstance(event, AssistantMessageEvent):
        return f"assistant: {event.message}"
    if isinstance(event, TurnCompletedEvent):
        return f"turn-completed turn_id={event.turn_id}"
    if isinstance(event, TurnCancelledEvent):
        return f"turn-cancelled turn_id={event.turn_id} reason={event.reason!r}"
    raise AssertionError("unreachable event type")


if __name__ == "__main__":
    app()
