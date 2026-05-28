"""Session and turn execution primitives for Phase 2."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from pinser.runtime.context.prompt import PromptContext, build_prompt_context
from pinser.runtime.conversation.messages import (
    AssistantMessage,
    ConversationItem,
    ToolResultMessage,
    UserMessage,
)
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

        self._state.turn_count = turn_state.turn_id
        self._state.transcript.append(UserMessage(content=turn_state.user_message))

        yield ProgressEvent(
            session_id=self._state.session_id,
            turn_id=turn_state.turn_id,
            stage="generating",
        )
        step = await self._generate_step(turn_state)
        while True:
            if cancellation_event is not None and cancellation_event.is_set():
                yield TurnCancelledEvent(
                    session_id=self._state.session_id,
                    turn_id=turn_state.turn_id,
                )
                return

            next_step, pending_events, transcript_items = await self._handle_assistant_step(
                turn_state, step
            )
            for event in pending_events:
                yield event
            self._state.transcript.extend(transcript_items)

            if next_step.tool_call is None:
                final_message = next_step.message or ""
                yield AssistantMessageEvent(
                    session_id=self._state.session_id,
                    turn_id=turn_state.turn_id,
                    message=final_message,
                )
                self._state.transcript.append(AssistantMessage(content=final_message))
                break

            step = next_step

        yield TurnCompletedEvent(
            session_id=self._state.session_id,
            turn_id=turn_state.turn_id,
        )

    async def _generate_step(self, turn_state: TurnState) -> AssistantStep:
        return await self._model.generate(
            build_prompt_context(self._state, turn_state.user_message)
        )

    async def _handle_assistant_step(
        self, turn_state: TurnState, step: AssistantStep
    ) -> tuple[AssistantStep, list[Event], list[ConversationItem]]:
        if step.tool_call is None:
            return step, [], []

        invocation = ToolInvocation(
            tool_name=step.tool_call.tool_name,
            arguments=step.tool_call.arguments,
        )
        tool = self._tools.get(invocation.tool_name)
        if tool is None:
            return AssistantStep(message=f"Tool {invocation.tool_name} is not available."), [], []

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
            result_message = ToolResultMessage(
                tool_name=invocation.tool_name,
                content="approval-required action blocked by dontAsk mode.",
                is_error=True,
            )
            return (
                AssistantStep(message="Denied: approval-required action blocked by dontAsk mode."),
                events
                + [
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
                ],
                [result_message],
            )
        if decision.kind is PermissionDecisionKind.DENY:
            denial_reason = decision.reason or "tool invocation denied."
            result_message = ToolResultMessage(
                tool_name=invocation.tool_name,
                content=denial_reason,
                is_error=True,
            )
            return (
                AssistantStep(message=f"Denied: {denial_reason}"),
                events
                + [
                    ToolDeniedEvent(
                        session_id=self._state.session_id,
                        turn_id=turn_state.turn_id,
                        tool_name=invocation.tool_name,
                        decision=PermissionDecisionKind.DENY,
                        reason=denial_reason,
                    )
                ],
                [result_message],
            )

        try:
            result = await tool.execute(invocation)
        except Exception as exc:
            error_text = str(exc)
            result_message = ToolResultMessage(
                tool_name=invocation.tool_name,
                content=error_text,
                is_error=True,
            )
            return (
                AssistantStep(message=f"Error: {error_text}"),
                events
                + [
                    ToolFailedEvent(
                        session_id=self._state.session_id,
                        turn_id=turn_state.turn_id,
                        tool_name=invocation.tool_name,
                        reason=error_text,
                    )
                ],
                [result_message],
            )

        events.append(
            ToolCompletedEvent(
                session_id=self._state.session_id,
                turn_id=turn_state.turn_id,
                tool_name=invocation.tool_name,
                summary=result.summary,
            )
        )
        rendered_result = self._render_tool_result_message(result)
        tool_result = ToolResultMessage(
            tool_name=invocation.tool_name,
            content=rendered_result,
        )
        self._state.transcript.append(tool_result)
        next_step = await self._generate_step(turn_state)
        return next_step, events, []

    def _render_tool_result_message(self, result: ToolExecutionResult) -> str:
        content = result.output.get("content")
        if isinstance(content, str):
            return content
        return result.summary
