# Phase 2 tool/runtime implementation note

This document records the intended Phase 2 runtime integration shape for tools in Pinser.

For canonical project phase status, see [`docs/project-roadmap.md`](../project-roadmap.md).

It is a local implementation note for contributors. It does not replace the architecture references.

Normative companion documents:

- [`../project-roadmap.md`](../project-roadmap.md)
- [`scope.md`](./scope.md)
- [`../architecture/interfaces-and-endpoints.md`](../architecture/interfaces-and-endpoints.md)
- [`../architecture/tool-contracts.md`](../architecture/tool-contracts.md)
- [`../architecture/permission-engine.md`](../architecture/permission-engine.md)
- [`../architecture/path-and-filesystem-safety.md`](../architecture/path-and-filesystem-safety.md)
- [`../architecture/bash-and-powershell-safety.md`](../architecture/bash-and-powershell-safety.md)
- [`../architecture/tool-input-streaming-and-partial-assembly.md`](../architecture/tool-input-streaming-and-partial-assembly.md)
- [`../architecture/tool-result-budgeting-and-dedup.md`](../architecture/tool-result-budgeting-and-dedup.md)
- [`../architecture/message-normalization-for-api.md`](../architecture/message-normalization-for-api.md)

## Purpose

Phase 2 needs a first real tool loop, but it should stay narrow.

This note defines a small Python-oriented integration shape that is consistent with the current architecture documentation while remaining appropriate for the current codebase, which still has:

- a Phase 1 in-memory session runtime
- a fake model backend
- no transcript persistence yet
- no remote/API execution surface yet

The goal is to make the first tool-capable turn implementation reviewable and extensible without prematurely implementing the full streamed tool executor described in the broader architecture documents.

## Scope

This note covers only the first local Phase 2 integration slice:

- Python tool interface shape
- permission-check hook shape
- event emission expectations for tool execution
- model -> permission -> tool -> tool-result -> continued model-response turn flow
- first-pass constraints that keep Phase 2 compatible with later persistence and normalization work

This note does not define:

- transcript persistence format
- final provider-facing message wire format
- retry/fallback state machine details
- full streaming partial-tool-input execution
- background shell lifecycle
- PowerShell support

## Phase 2 design constraints derived from architecture docs

The following constraints are already established by the architecture references and should shape the Phase 2 implementation.

### 1. Tools are first-class runtime capabilities

Per [`../architecture/interfaces-and-endpoints.md`](../architecture/interfaces-and-endpoints.md) and [`../architecture/tool-contracts.md`](../architecture/tool-contracts.md), a tool is not just an execute callback.

The Phase 2 Python implementation should preserve at least these responsibilities per tool:

- stable name
- typed input validation
- typed output/result object
- tool-specific permission hook
- execution logic
- concurrency/read-only metadata where useful
- model-visible result rendering

Phase 2 does not need to expose every future capability immediately, but it should not collapse tools into ad hoc string branching inside session code.

### 2. Permission evaluation is layered

Per [`../architecture/permission-engine.md`](../architecture/permission-engine.md), permission decisions are layered:

1. global whole-tool checks
2. tool-specific content-sensitive checks
3. mode-specific transformation
4. final surfaced result: `allow`, `ask`, or `deny`

Phase 2 should preserve that layering even if it only actively supports:

- `default`
- `dontAsk`

### 3. Progress is UI/runtime state, not durable conversation content

Per [`../architecture/message-normalization-for-api.md`](../architecture/message-normalization-for-api.md) and [`../architecture/transcript-and-persistence-semantics.md`](../architecture/transcript-and-persistence-semantics.md):

- progress is runtime/UI-only
- progress must not be treated as durable conversation content
- later model-facing normalization must be able to exclude progress cleanly

Phase 2 event design must preserve this distinction.

### 4. Tool use must still close with a tool result shape

The broader architecture requires `tool_use` / `tool_result` closure, including synthetic results on abandon/failure paths.

Phase 2 is not yet implementing the full provider-facing `tool_use` content-block protocol, but it should still preserve the same conceptual boundary:

- the assistant requests a tool action
- the runtime executes or blocks it
- the runtime produces a tool result object
- the continued assistant step consumes that result

Phase 2 can model this in Python-native structures first, as long as it does not erase the distinction between:

- tool execution telemetry for the CLI
- model-facing tool result content

### 5. Read-before-write and stale-read checks are part of tool permission/safety semantics

Per [`../architecture/path-and-filesystem-safety.md`](../architecture/path-and-filesystem-safety.md), file mutation safety is not just validation after the fact.

For `Edit` and `FileWrite`, the Phase 2 tool path must preserve:

- prior full-read requirement
- partial-read does not authorize mutation
- stale-read check immediately before write
- a tight check/write critical section with no avoidable async gap

## Proposed Python tool interface shape

A Phase 2 tool should be represented by a first-class object or protocol, conceptually shaped like:

```python
class Tool(Protocol[ToolInputT, ToolResultT]):
    name: str
    read_only: bool
    concurrency_safe: bool

    def validate_input(self, raw_input: object) -> ToolInputT: ...

    def check_permissions(
        self,
        invocation: ToolInvocation[ToolInputT],
        context: PermissionContext,
    ) -> PermissionDecision | PermissionPassthrough: ...

    async def execute(
        self,
        invocation: ToolInvocation[ToolInputT],
        runtime_context: ToolRuntimeContext,
    ) -> ToolExecutionResult[ToolResultT]: ...

    def render_result_for_model(
        self,
        result: ToolExecutionResult[ToolResultT],
    ) -> ToolResultContent: ...
```

The exact Python typing may differ, but the following shape should be preserved.

### Required per-tool concepts

#### Stable tool identity

Every tool must have a stable canonical name such as:

- `Read`
- `Edit`
- `FileWrite`
- `Glob`
- `Grep`
- `Bash`

#### Validated input object

Tool execution should not operate directly on unvalidated raw dicts.

For Phase 2, pydantic models or equivalent typed dataclasses are acceptable.

#### Tool-specific permission hook

Each tool must be able to inspect its own validated input and return a permission-oriented outcome before execution.

This is especially important for:

- file path checks
- read-before-write and stale-read enforcement
- Bash command-sensitive checks

#### Structured execution result

Execution should return a structured result object, not just rendered text.

A minimal Phase 2 result should preserve room for:

- success/failure state
- structured output payload
- model-visible text/content
- optional metadata useful for the runtime or CLI

#### Model-visible rendering boundary

Per the broader tool-result architecture, the model-facing tool result representation should remain a separate concern from internal runtime state and from CLI logs.

Phase 2 does not need the full final formatting/budgeting layer yet, but it should keep this boundary explicit.

## Proposed supporting runtime types

The following conceptual shapes are recommended for Phase 2.

### Tool invocation

```python
@dataclass(frozen=True)
class ToolInvocation(Generic[ToolInputT]):
    tool_name: str
    tool_call_id: str
    input: ToolInputT
```

Notes:

- `tool_call_id` should exist even in the first local implementation because later phases will need a stable pairing anchor between tool requests and tool results
- the identifier may be runtime-local in Phase 2

### Tool runtime context

```python
@dataclass
class ToolRuntimeContext:
    workspace_root: Path
    session_state: SessionState
    read_tracker: ReadTracker
    permission_context: PermissionContext
```

This context should stay narrow in Phase 2.

It should supply only what local tools need to run safely.

### Tool execution result

```python
@dataclass(frozen=True)
class ToolExecutionResult(Generic[ToolResultT]):
    success: bool
    output: ToolResultT | None
    model_content: str
    is_error: bool = False
    prevent_continuation: bool = False
```

Notes:

- `prevent_continuation` is optional for the first implementation, but the architecture already anticipates tool outcomes that may terminate or block continued model progression
- the exact field names may differ, but success/error state plus model-facing content should remain explicit

## Permission hook shape

The tool-specific permission hook should conceptually look like:

```python
def check_permissions(
    invocation: ToolInvocation[ToolInputT],
    context: PermissionContext,
) -> PermissionDecision | PermissionPassthrough:
    ...
```

### Phase 2 permission decision model

At minimum, the runtime should preserve explicit final outcomes:

- `allow`
- `ask`
- `deny`

A small internal `passthrough`-style outcome is also reasonable if it helps preserve the layering described in [`../architecture/permission-engine.md`](../architecture/permission-engine.md), where unresolved tool-specific checks are converted later by the global engine.

### Recommended decision fields

A Phase 2 decision object should leave room for:

- `behavior`: `allow` / `ask` / `deny`
- machine-readable reason code
- user-visible message
- optional updated input

The optional updated input matters because the architecture notes that permission evaluation may return an allow plus normalized input.

### Required evaluation ordering in Phase 2

Phase 2 should preserve this reduced version of the architecture ordering:

1. whole-tool deny
2. whole-tool ask
3. tool-specific permission check
4. bypass-immune deny/ask style checks from the tool layer
5. whole-tool allow
6. unresolved -> `ask`
7. `dontAsk` transforms final `ask` to `deny`

Even if only a small subset of modes is active, the ordering should remain deny/ask first and broad allow later.

### Implications for file tools

For file tools, the permission hook or the shared path-safety layer it calls into should be able to express at least:

- blocked by workspace boundary
- blocked by protected path
- approval required for suspicious/dangerous path
- mutation blocked because file was not fully read
- mutation blocked because file changed since last read

### Implications for Bash

For Bash, the permission hook should be able to express at least:

- denied by whole-tool rule
- denied by command-sensitive rule
- approval required for non-read-only or suspicious command
- allow for clearly read-only command under current rules

## Event emission expectations for tool execution

Phase 2 should extend the current event model conservatively.

The event model should preserve a distinction between:

- lifecycle events
- conversation content events
- progress/runtime events
- tool execution events
- permission/action-required events

### Minimum new event categories for Phase 2

At minimum, the runtime should support tool/permission events conceptually equivalent to:

- `tool-call-started`
- `tool-call-completed`
- `tool-call-failed`
- `permission-required`
- `tool-call-denied`

A dedicated tool-result event is also reasonable if the implementation benefits from distinguishing:

- execution completion
- model-visible returned result content

### Event semantics

#### Tool start/run events are runtime-visible

A tool-started event is for the runtime/UI.
It should not be treated as durable conversation content.

#### Permission-required events are action-required, not success or progress

A permission-required event should be separate from plain progress output because it signals a blocked continuation pending explicit approval.

#### Denial and blocked-mutation events should be explicit

For example:

- policy deny
- read-before-write block
- stale-read block

These should not be collapsed into a generic exception event if the runtime knows the specific reason.

#### Final tool result should remain conceptually distinct from CLI telemetry

The CLI may render a brief running/completed line, while the model-facing tool result content remains separately tracked.

This follows the separation described in [`../architecture/tool-result-budgeting-and-dedup.md`](../architecture/tool-result-budgeting-and-dedup.md).

## Expected Phase 2 turn shape for tool-using turns

This section defines the intended local turn flow.

Phase 2 does not need full provider-streamed partial tool assembly yet. The first implementation can use a simpler loop while preserving the same conceptual states.

### Conceptual flow

```text
user message
-> model step produces assistant content and/or tool request
-> runtime validates tool input
-> runtime evaluates permission decision
-> if allow: execute tool
-> runtime emits tool result
-> runtime continues model step with tool result context
-> assistant completes turn
```

### Recommended concrete loop for the first implementation

1. Emit `turn-started`
2. Emit user message event
3. Emit progress for model generation
4. Ask the model backend for the next assistant step
5. If the assistant step is plain assistant text:
   - emit assistant content
   - complete the turn
6. If the assistant step is a tool request:
   - validate tool input
   - emit tool-started or tool-planned event as appropriate
   - run permission evaluation
   - if permission is `deny`:
     - emit tool-denied event
     - synthesize an error-like tool result object
     - continue the assistant loop with that tool result in context
   - if permission is `ask`:
     - emit permission-required event
     - in `dontAsk`, convert to denial and proceed as above
     - in interactive default mode, the first implementation may still fail clearly if interactive approval has not yet been wired
   - if permission is `allow`:
     - execute tool
     - emit tool completion/result event
     - continue the assistant loop with the tool result in context
7. Emit final assistant message event
8. Emit `turn-completed`

### Important continuation rule

A denied or failed tool invocation should generally still produce a tool result object for the continued assistant step rather than crashing the whole turn, unless the failure is a true runtime bug.

This keeps Phase 2 aligned with the architecture’s closure expectations for tool requests and results.

## Tool result attachment to the current Phase 1 event model

The current runtime stores only user and assistant conversation items in transcript state and treats progress separately.

Phase 2 should keep that discipline.

### Phase 2 local rule

For the in-memory session runtime:

- user and assistant conversational content remain transcript items
- progress and tool-running telemetry remain non-transcript runtime events
- model-facing tool result objects should be stored in turn-local continuation state, not naively appended as assistant text

This is important because later architecture requires special handling for tool results during normalization, ordering, budgeting, and persistence.

### Practical implication

Even if the first local implementation temporarily uses a simplified internal representation, it should not flatten tool results into plain assistant prose inside the session transcript.

Instead, it should keep an explicit internal tool-result representation that future Phase 3 and Phase 4 work can normalize correctly.

## Simplifications explicitly allowed in Phase 2

The following simplifications are acceptable in the first Phase 2 implementation as long as the boundaries above are preserved.

### 1. No eager partial-input streaming yet

The first implementation may wait until a tool request is fully formed before executing it.

This is acceptable because the full streaming executor architecture is a later compatibility layer.

### 2. No concurrent multi-tool execution yet

The first implementation may execute one tool request at a time in deterministic order.

This remains compatible with the broader architecture if tool objects still carry concurrency metadata.

### 3. No transcript persistence yet

Tool events and tool results may remain in-memory only for Phase 2.

But event categories should remain persistence-friendly.

### 4. No aggressive tool-result budgeting yet

The first implementation may use straightforward model-visible tool result rendering.

It should still preserve:

- explicit error-vs-success distinction
- a stable result object boundary
- one result per completed tool request

## Non-goals for this note

This note does not authorize Phase 2 to silently expand into:

- PowerShell parity
- notebook editing
- background Bash lifecycle
- classifier-mediated permission modes
- full retry/fallback executor repair
- remote/API transport wiring

Those remain deferred exactly as documented in [`scope.md`](./scope.md) and [`../project-roadmap.md`](../project-roadmap.md).

## Bottom line

For Phase 2, Pinser should implement a small but explicit local tool loop with:

- first-class Python tools
- layered permission checking
- explicit runtime events for tool and permission states
- structured tool results distinct from progress/CLI telemetry
- a continued assistant loop that consumes tool results rather than treating tools as side effects outside the turn

That gives the project a usable local coding-assistant core while staying aligned with the broader architecture documentation.