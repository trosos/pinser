"""Typer CLI for Pinser."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

from pinser.app.config.settings import load_settings
from pinser.runtime.engine.session import Session, SessionState
from pinser.runtime.events.models import (
    AssistantMessageEvent,
    Event,
    TurnCancelledEvent,
    TurnCompletedEvent,
    TurnStartedEvent,
)
from pinser.runtime.model.fake import FakeModel

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
    session = Session(
        SessionState(session_id=str(uuid4())),
        FakeModel(),
    )

    events = asyncio.run(_collect_events(session, message))
    for event in events:
        typer.echo(_render_event(event))


def _render_event(event: Event) -> str:
    if isinstance(event, TurnStartedEvent):
        return f"turn-started turn_id={event.turn_id} user={event.user_message}"
    if isinstance(event, AssistantMessageEvent):
        return f"assistant: {event.message}"
    if isinstance(event, TurnCompletedEvent):
        return f"turn-completed turn_id={event.turn_id}"
    if isinstance(event, TurnCancelledEvent):
        return f"turn-cancelled turn_id={event.turn_id}"
    raise AssertionError("unreachable event type")


async def _collect_events(session: Session, message: str) -> list[Event]:
    return [event async for event in session.run_turn(message)]


if __name__ == "__main__":
    app()
