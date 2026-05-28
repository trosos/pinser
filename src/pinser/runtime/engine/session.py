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
from pinser.runtime.engine.file_state import FileStateTracker
from pinser.runtime.events.models import (
    AssistantMessageEvent,
    Event,
    PermissionRequiredEvent,
    ProgressEvent,
    ToolBlockedEvent,
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
from pinser.runtime.tools.protocol import ToolExecutionResult, ToolInvocation
from pinser.runtime.tools.registry import ToolRegistry
from pinser.runtime.tools_errors import ToolExecutionError, ToolSafetyBlockedError

MAX_ASSISTANT_STEPS_PER_TURN = 8


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
    workspace_root: Path | None = None
    turn_count: int = 0
    transcript: list[ConversationItem] = field(default_factory=list)
    file_state: FileStateTracker = field(init=False)

    def __post_init__(self) -> None:
        root = (self.workspace_root or Path.cwd()).resolve()
        self.workspace_root = root
        self.file_state = FileStateTracker(workspace_root=root)


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
        self._workspace_root = (workspace_root or state.workspace_root or Path.cwd()).resolve()
        if self._state.workspace_root != self._workspace_root:
            self._state.workspace_root = self._workspace_root
            self._state.file_state = FileStateTracker(workspace_root=self._workspace_root)
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
        step_count = 1
        while True:
            if cancellation_event is not None and cancellation_event.is_set():
                yield TurnCancelledEvent(
                    session_id=self._state.session_id,
                    turn_id=turn_state.turn_id,
                )
                return

            if step.tool_call is not None and step_count >= MAX_ASSISTANT_STEPS_PER_TURN:
                limit_message = (
                    "Stopped: exceeded maximum assistant/tool steps for a single turn."
                )
                yield AssistantMessageEvent(
                    session_id=self._state.session_id,
                    turn_id=turn_state.turn_id,
                    message=limit_message,
                )
                self._state.transcript.append(AssistantMessage(content=limit_message))
                break

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

            step_count += 1
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
            return self._permission_denied_response(
                turn_id=turn_state.turn_id,
                tool_name=invocation.tool_name,
                events=events,
                permission_required=True,
                summary=permission_request.summary,
                resource=permission_request.resource,
                reason="approval-required action blocked by dontAsk mode.",
            )
        if decision.kind is PermissionDecisionKind.DENY:
            denial_reason = decision.reason or "tool invocation denied."
            return self._permission_denied_response(
                turn_id=turn_state.turn_id,
                tool_name=invocation.tool_name,
                events=events,
                permission_required=False,
                summary=permission_request.summary,
                resource=permission_request.resource,
                reason=denial_reason,
            )

        try:
            result = await tool.execute(invocation)
        except ToolSafetyBlockedError as exc:
            return self._blocked_response(
                turn_id=turn_state.turn_id,
                tool_name=invocation.tool_name,
                events=events,
                reason=str(exc),
            )
        except ToolExecutionError as exc:
            return self._failed_response(
                turn_id=turn_state.turn_id,
                tool_name=invocation.tool_name,
                events=events,
                reason=str(exc),
            )
        except Exception as exc:
            return self._failed_response(
                turn_id=turn_state.turn_id,
                tool_name=invocation.tool_name,
                events=events,
                reason=str(exc),
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

    def _permission_denied_response(
        self,
        *,
        turn_id: int,
        tool_name: str,
        events: list[Event],
        permission_required: bool,
        summary: str,
        resource: str | None,
        reason: str,
    ) -> tuple[AssistantStep, list[Event], list[ConversationItem]]:
        result_message = ToolResultMessage(
            tool_name=tool_name,
            content=reason,
            is_error=True,
        )
        denied_events = list(events)
        if permission_required:
            denied_events.append(
                PermissionRequiredEvent(
                    session_id=self._state.session_id,
                    turn_id=turn_id,
                    tool_name=tool_name,
                    summary=summary,
                    resource=resource,
                )
            )
        denied_events.append(
            ToolDeniedEvent(
                session_id=self._state.session_id,
                turn_id=turn_id,
                tool_name=tool_name,
                decision=PermissionDecisionKind.DENY,
                reason=reason,
            )
        )
        return (
            AssistantStep(message=f"Denied: {reason}"),
            denied_events,
            [result_message],
        )

    def _blocked_response(
        self,
        *,
        turn_id: int,
        tool_name: str,
        events: list[Event],
        reason: str,
    ) -> tuple[AssistantStep, list[Event], list[ConversationItem]]:
        result_message = ToolResultMessage(
            tool_name=tool_name,
            content=reason,
            is_error=True,
        )
        return (
            AssistantStep(message=f"Blocked: {reason}"),
            events
            + [
                ToolBlockedEvent(
                    session_id=self._state.session_id,
                    turn_id=turn_id,
                    tool_name=tool_name,
                    reason=reason,
                )
            ],
            [result_message],
        )

    def _failed_response(
        self,
        *,
        turn_id: int,
        tool_name: str,
        events: list[Event],
        reason: str,
    ) -> tuple[AssistantStep, list[Event], list[ConversationItem]]:
        result_message = ToolResultMessage(
            tool_name=tool_name,
            content=reason,
            is_error=True,
        )
        return (
            AssistantStep(message=f"Error: {reason}"),
            events
            + [
                ToolFailedEvent(
                    session_id=self._state.session_id,
                    turn_id=turn_id,
                    tool_name=tool_name,
                    reason=reason,
                )
            ],
            [result_message],
        )
