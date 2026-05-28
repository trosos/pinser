"""Session and turn execution primitives for Phase 2."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from pinser.runtime.context.prompt import PromptContext, build_prompt_context
from pinser.runtime.conversation.messages import AssistantMessage, ConversationItem, UserMessage
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
from pinser.runtime.model.messages import AssistantStep
from pinser.runtime.model.protocol import ModelBackend
from pinser.runtime.permissions import PermissionDecisionKind
from pinser.runtime.tools import ToolExecutionResult, ToolInvocation, ToolRegistry


@dataclass(frozen=True, slots=True)
class TurnState:
    """Per-turn derived state used during execution."""

    turn_id: int
    user_message: str
    prompt_context: PromptContext


@dataclass(slots=True)
class SessionState:
    """Conversation state that persists across turns in memory."""

    session_id: str
    turn_count: int = 0
    transcript: list[ConversationItem] = field(default_factory=list)


class Session:
    """Minimal conversation session with async event streaming."""

    def __init__(
        self,
        state: SessionState,
        model: ModelBackend,
        *,
        workspace_root: Path | None = None,
        tools: ToolRegistry | None = None,
    ) -> None:
        self._state = state
        self._model = model
        self._workspace_root = (workspace_root or Path.cwd()).resolve()
        self._tools = tools or ToolRegistry()

    @property
    def state(self) -> SessionState:
        """Return the persistent session state."""

        return self._state

    @property
    def workspace_root(self) -> Path:
        """Return the workspace root used by the session."""

        return self._workspace_root

    def prepare_turn(self, user_message: str) -> TurnState:
        """Build explicit per-turn state before model execution."""

        return TurnState(
            turn_id=self._state.turn_count + 1,
            user_message=user_message,
            prompt_context=build_prompt_context(self._state, user_message),
        )

    async def run_turn(
        self,
        user_message: str,
        *,
        cancellation_event: asyncio.Event | None = None,
    ) -> AsyncIterator[Event]:
        """Execute one turn and stream ordered runtime events."""

        turn_state = self.prepare_turn(user_message)
        pending_events: list[Event] = []

        yield TurnStartedEvent(
            session_id=self._state.session_id,
            turn_id=turn_state.turn_id,
            user_message=turn_state.user_message,
        )
        yield UserMessageEvent(
            session_id=self._state.session_id,
            turn_id=turn_state.turn_id,
            message=turn_state.user_message,
        )

        if cancellation_event is not None and cancellation_event.is_set():
            yield TurnCancelledEvent(
                session_id=self._state.session_id,
                turn_id=turn_state.turn_id,
            )
            return

        yield ProgressEvent(
            session_id=self._state.session_id,
            turn_id=turn_state.turn_id,
            stage="generating",
        )
        step = await self._model.generate(turn_state.prompt_context)
        final_message, pending_events = await self._handle_assistant_step(turn_state, step)

        if cancellation_event is not None and cancellation_event.is_set():
            yield TurnCancelledEvent(
                session_id=self._state.session_id,
                turn_id=turn_state.turn_id,
            )
            return

        for event in pending_events:
            yield event
        yield AssistantMessageEvent(
            session_id=self._state.session_id,
            turn_id=turn_state.turn_id,
            message=final_message,
        )

        self._state.turn_count = turn_state.turn_id
        self._state.transcript.extend(
            (
                UserMessage(content=turn_state.user_message),
                AssistantMessage(content=final_message),
            )
        )
        yield TurnCompletedEvent(
            session_id=self._state.session_id,
            turn_id=turn_state.turn_id,
        )

    async def _handle_assistant_step(
        self, turn_state: TurnState, step: AssistantStep
    ) -> tuple[str, list[Event]]:
        if step.tool_call is None:
            return step.message or "", []

        invocation = ToolInvocation(
            tool_name=step.tool_call.tool_name,
            arguments=step.tool_call.arguments,
        )
        tool = self._tools.get(invocation.tool_name)
        if tool is None:
            return f"Tool {invocation.tool_name} is not available.", []

        permission_request = tool.build_permission_request(invocation)
        events: list[Event] = [
            ToolStartedEvent(
                session_id=self._state.session_id,
                turn_id=turn_state.turn_id,
                tool_name=invocation.tool_name,
                summary=permission_request.summary,
            )
        ]
        decision = tool.decide_permission(invocation)
        if decision.kind is PermissionDecisionKind.ASK:
            events.extend(
                [
                    PermissionRequiredEvent(
                        session_id=self._state.session_id,
                        turn_id=turn_state.turn_id,
                        tool_name=invocation.tool_name,
                        summary=permission_request.summary,
                        resource=permission_request.resource,
                    ),
                    ToolDeniedEvent(
                        session_id=self._state.session_id,
                        turn_id=turn_state.turn_id,
                        tool_name=invocation.tool_name,
                        decision=PermissionDecisionKind.DENY,
                        reason="approval-required action blocked by dontAsk mode.",
                    ),
                ]
            )
            return "Denied: approval-required action blocked by dontAsk mode.", events
        if decision.kind is PermissionDecisionKind.DENY:
            events.append(
                ToolDeniedEvent(
                    session_id=self._state.session_id,
                    turn_id=turn_state.turn_id,
                    tool_name=invocation.tool_name,
                    decision=PermissionDecisionKind.DENY,
                    reason=decision.reason or "tool invocation denied.",
                )
            )
            return f"Denied: {decision.reason or 'tool invocation denied.'}", events

        try:
            result = await tool.execute(invocation)
        except Exception as exc:
            events.append(
                ToolFailedEvent(
                    session_id=self._state.session_id,
                    turn_id=turn_state.turn_id,
                    tool_name=invocation.tool_name,
                    reason=str(exc),
                )
            )
            return f"Error: {exc}", events

        events.append(
            ToolCompletedEvent(
                session_id=self._state.session_id,
                turn_id=turn_state.turn_id,
                tool_name=invocation.tool_name,
                summary=result.summary,
            )
        )
        return self._render_tool_result_message(result), events

    def _render_tool_result_message(self, result: ToolExecutionResult) -> str:
        content = result.output.get("content")
        if isinstance(content, str):
            return content
        return result.summary
