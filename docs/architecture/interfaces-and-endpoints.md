# Interfaces and integration boundaries

This document identifies the runtime interfaces and integration boundaries that matter for a clean-room rewrite.

It is intentionally complementary to:
- `docs/tool-contracts.md`
- `docs/remote-api.md`

Those two documents contain the detailed per-tool and per-endpoint contracts.
This document focuses instead on the higher-level interfaces that connect major subsystems, and on the invariants those interfaces must preserve.

Primary inspected sources:
- `src/Tool.ts`
- `src/tools.ts`
- `src/QueryEngine.ts`
- `src/query.ts`
- `src/Task.ts`
- `src/tasks.ts`
- `src/utils/tasks.ts`
- `src/utils/swarm/backends/types.ts`
- `src/utils/swarm/backends/InProcessBackend.ts`

Where deeper implementation files were not available, this document stays at the level of directly verified interface and callsite behavior.

---

## 1. How to use this document

Use this document to answer:
- what the major runtime boundaries are
- what data and capabilities pass across them
- which invariants a rewrite must preserve
- which details are intentionally delegated to the more specific tool/API docs

Use the other docs when you need lower-level detail:
- for concrete tool input/output/result contracts: `docs/tool-contracts.md`
- for HTTP methods, headers, and payloads: `docs/remote-api.md`

---

## 2. Preservation principles

A compatible rewrite must preserve the following interface-level properties.

### 2.1 Conversation engine boundary
A conversation engine instance is a long-lived object representing one conversation/session.
It is created once with its dependencies and then accepts multiple user submissions over time.

Preserve:
- one engine instance per conversation
- session-local mutable transcript state
- injected dependencies rather than hard-coded globals
- async-streaming turn execution rather than request/response buffering

### 2.2 Turn execution boundary
A single user submission expands into a full turn lifecycle that can include:
- message normalization
- slash-command handling
- model streaming
- tool execution
- retries/fallbacks
- persistence updates
- terminal completion state

Preserve:
- these phases occurring inside one logical turn API call
- retries and model fallback remaining in-turn rather than requiring the caller to restart the turn

### 2.3 Tool boundary
A tool is a first-class capability object, not just an execute callback.

Preserve:
- per-tool schema
- validation and permission logic
- execution logic
- result rendering/mapping
- concurrency and safety declarations
- tool-specific progress reporting

Detailed per-tool requirements are defined in `docs/tool-contracts.md`.

### 2.4 Runtime task boundary
Background work is represented as typed tasks with stable status values and lifecycle control.

Preserve:
- typed task kinds
- stable task statuses
- kill/stop semantics
- app-state visibility of live tasks
- output retrieval through task-oriented interfaces

### 2.5 Team/backend boundary
Teammate execution is abstracted behind a backend interface so different execution media can be used behind a common orchestration layer.

Preserve:
- backend-agnostic spawn/send/terminate/kill/isActive operations
- distinction between pane-based and in-process execution backends
- message-oriented communication across backends

### 2.6 Persistence boundary
Prompt history, session transcript persistence, and file-backed team task lists are separate surfaces with different purposes.

Preserve:
- prompt history separate from conversation transcript storage
- durable team task-list coordination semantics
- resumability-oriented transcript persistence behavior

---

## 3. Core conversation engine interfaces

## 3.1 `QueryEngineConfig`
**File:** `src/QueryEngine.ts`

This is the top-level configuration and dependency contract for a conversation engine instance.

### Verified shape

```ts
export type QueryEngineConfig = {
  cwd: string
  tools: Tools
  commands: Command[]
  mcpClients: MCPServerConnection[]
  agents: AgentDefinition[]
  canUseTool: CanUseToolFn
  getAppState: () => AppState
  setAppState: (f: (prev: AppState) => AppState) => void
  initialMessages?: Message[]
  readFileCache: FileStateCache
  customSystemPrompt?: string
  appendSystemPrompt?: string
  userSpecifiedModel?: string
  fallbackModel?: string
  thinkingConfig?: ThinkingConfig
  maxTurns?: number
  maxBudgetUsd?: number
  taskBudget?: { total: number }
  jsonSchema?: Record<string, unknown>
  verbose?: boolean
  replayUserMessages?: boolean
  handleElicitation?: ToolUseContext['handleElicitation']
  includePartialMessages?: boolean
  setSDKStatus?: (status: SDKStatus) => void
  abortController?: AbortController
  orphanedPermission?: OrphanedPermission
  snipReplay?: (
    yieldedSystemMsg: Message,
    store: Message[],
  ) => { messages: Message[]; executed: boolean } | undefined
}
```

### Interface meaning
This boundary supplies the engine with:
- execution environment (`cwd`)
- capability set (`tools`, `commands`, `mcpClients`, `agents`)
- permission enforcement (`canUseTool`)
- global session/app hooks (`getAppState`, `setAppState`)
- persisted/resumed transcript seed (`initialMessages`)
- per-session caches and policies (`readFileCache`, prompts, model settings, budgets)
- SDK/transport callbacks (`setSDKStatus`)
- interruption control (`abortController`)

### Preservation requirement
A rewrite must preserve the architectural shape even if the type is refactored:
- engine dependencies are supplied at construction time
- the engine owns session-local mutable state after construction
- cancellation can be injected
- model/prompt policy can be overridden per engine instance
- app-state access is explicit rather than hidden behind globals

### Refactor-safe changes
A rewrite may split this into smaller configuration/service objects if the same capabilities remain available to the engine.

---

## 3.2 `QueryEngine.submitMessage()`
**File:** `src/QueryEngine.ts`

### Verified shape

```ts
async *submitMessage(
  prompt: string | ContentBlockParam[],
  options?: { uuid?: string; isMeta?: boolean },
): AsyncGenerator<SDKMessage, void, unknown>
```

### Interface meaning
This is the primary session-turn API in headless/SDK usage.

It accepts:
- raw text input
- or structured content blocks
- plus optional metadata including caller-provided UUID and meta-message classification

It yields:
- a streamed sequence of SDK-visible messages/events representing the full turn lifecycle

### Preservation requirement
A compatible rewrite must preserve:
- acceptance of both string and structured content inputs
- async streaming rather than buffered final-only output
- one call corresponding to one logical turn submission
- the ability for a caller-provided UUID to flow through where required by downstream transports

### Important behavioral invariant
The caller should not have to separately orchestrate:
- slash-command preprocessing
- transcript persistence startup
- model loop invocation
- tool follow-up iterations

Those remain responsibilities of `submitMessage()` and the lower query engine stack.

---

## 3.3 `query()`
**File:** `src/query.ts`

### Verified shape

```ts
export async function* query(
  params: QueryParams,
): AsyncGenerator<
  | StreamEvent
  | RequestStartEvent
  | Message
  | TombstoneMessage
  | ToolUseSummaryMessage,
  Terminal
>
```

### Verified parameter shape

```ts
export type QueryParams = {
  messages: Message[]
  systemPrompt: SystemPrompt
  userContext: { [k: string]: string }
  systemContext: { [k: string]: string }
  canUseTool: CanUseToolFn
  toolUseContext: ToolUseContext
  fallbackModel?: string
  querySource: QuerySource
  maxOutputTokensOverride?: number
  maxTurns?: number
  skipCacheWrite?: boolean
  taskBudget?: { total: number }
  deps?: QueryDeps
}
```

### Interface meaning
This is the turn-runtime boundary between:
- session-level orchestration
- the recursive model/tool execution loop

### Preservation requirement
A compatible rewrite must preserve:
- async-generator form
- mixed yielded event families, not just assistant text
- a returned terminal result object in addition to yielded events
- in-loop retries/recovery/fallback behavior
- tool execution occurring as part of the same logical turn flow

### What this document does not restate
The exact event families and tool-result semantics are documented elsewhere when more specific detail exists.
This document focuses on the fact that `query()` is the streaming kernel boundary.

---

## 4. Message and event model boundary

## 4.1 Message/event families
**Files:** `src/query.ts`, `src/Tool.ts`, `src/QueryEngine.ts`

Verified important families include:
- `user`
- `assistant`
- `system`
- `attachment`
- `progress`
- `stream_event`
- `stream_request_start`
- `tool_use_summary`
- `tombstone`

### Interface meaning
The runtime operates on an event-rich transcript model, not a minimal chat-only model.

### Preservation requirement
A rewrite must preserve the distinction between at least:
- canonical transcript messages
- ephemeral progress/streaming events
- repair/removal events such as tombstones
- structural/system events such as compact boundaries and local command output

### Why this matters
If these are collapsed into one undifferentiated chat-message type, the rewrite will lose:
- recovery semantics
- transcript repair semantics
- transport/UI projection flexibility
- compaction structure

---

## 4.2 Compaction/snipping structure
Compaction boundaries are represented as transcript-visible structural messages, and replay/snip logic can project a reduced message view while preserving session continuity.

### Preservation requirement
A rewrite must preserve:
- explicit compact boundary structure in the conversation history model
- the ability to replay a projected/snipped view without destroying the underlying turn continuity model

This does not require the same internal implementation, but it does require an equivalent structural concept.

---

## 5. Tool system interfaces

## 5.1 `Tool`
**File:** `src/Tool.ts`

This is the central runtime abstraction for callable capabilities.

### Verified capability areas
A tool carries:
- identity: `name`, aliases, search metadata
- schemas: input and optional output schema information
- prompt metadata: description and prompt text/providers
- permissions: validation, permission checking, permission matcher preparation
- execution: `call(...)`
- safety declarations: read-only, destructive, concurrency-safe, interrupt behavior
- transcript/UI rendering: tool-use/result/progress/rejection/error renderers
- search/indexing helpers and summarization helpers
- runtime policy flags: defer/always-load/strict/interaction requirements
- integration metadata: MCP/LSP/etc.

### Preservation requirement
A compatible rewrite must preserve the fact that a tool is a compound object that combines:
- model-facing schema
- runtime execution
- permission policy
- rendering behavior
- safety metadata

### Explicit non-goal
This document does not restate each tool’s individual input/output schema.
Those are documented in `docs/tool-contracts.md` where inspected directly.

---

## 5.2 Key `Tool` methods and their boundary meaning
Representative methods verified in `Tool.ts` include:

```ts
call(args, context, canUseTool, parentMessage, onProgress?)
description(input, options)
prompt(options)
checkPermissions(input, context)
validateInput?(input, context)
renderToolUseMessage(input, options)
renderToolResultMessage?(content, progressMessagesForMessage, options)
mapToolResultToToolResultBlockParam(content, toolUseID)
```

### Preservation requirement
A rewrite must preserve these categories of tool behavior:
- executable call path
- model-visible description/prompt material
- validation before execution
- permission checking before execution
- rendering/mapping of runtime output into transcript-visible tool results
- optional progress emission during tool execution

The exact method names can change if the behavior categories remain explicit and complete.

---

## 5.3 `ToolUseContext`
**File:** `src/Tool.ts`

This is the runtime dependency object passed into tool execution.

### Verified capability domains carried inside it
- available commands/tools/resources and mode options
- cancellation via abort controller
- read-file state
- app-state accessors
- current message context
- elicitation/prompt hooks
- notification hooks
- file history and attribution update hooks
- system-prompt context
- agent identity metadata
- content replacement / tool-result budget state

### Preservation requirement
A rewrite does not need to preserve the exact giant bag type, but it must preserve the capability surface that tools rely on:
- access to current session/runtime state
- controlled mutation of app state
- access to current message context when needed
- cancellation visibility
- access to allowed tools/commands/resources
- agent identity visibility for subagent contexts
- optional human elicitation hooks

### Rewrite guidance
This is a good candidate to split into smaller injected services, but only if the full capability surface remains available.

---

## 5.4 `ToolPermissionContext`
**File:** `src/Tool.ts`

### Verified shape summary

```ts
export type ToolPermissionContext = DeepImmutable<{
  mode: PermissionMode
  additionalWorkingDirectories: Map<string, AdditionalWorkingDirectory>
  alwaysAllowRules: ToolPermissionRulesBySource
  alwaysDenyRules: ToolPermissionRulesBySource
  alwaysAskRules: ToolPermissionRulesBySource
  isBypassPermissionsModeAvailable: boolean
  isAutoModeAvailable?: boolean
  strippedDangerousRules?: ToolPermissionRulesBySource
  shouldAvoidPermissionPrompts?: boolean
  awaitAutomatedChecksBeforeDialog?: boolean
  prePlanMode?: PermissionMode
}>
```

### Interface meaning
This is the policy context used to:
- filter tool visibility
- determine allow/deny/ask behavior
- shape interactive vs automated execution behavior

### Preservation requirement
A rewrite must preserve:
- permission mode as explicit tool-system input
- distinct allow/deny/ask rule sets
- ability to suppress permission prompts in automated/background contexts
- ability to temporarily modify permission mode for plan-mode flows and restore it later

---

## 5.5 Tool registry and tool-pool assembly
**File:** `src/tools.ts`

Verified important functions:

```ts
getAllBaseTools(): Tools
getTools(permissionContext: ToolPermissionContext): Tools
assembleToolPool(permissionContext: ToolPermissionContext, mcpTools: Tools): Tools
getMergedTools(permissionContext: ToolPermissionContext, mcpTools: Tools): Tools
```

### Interface meaning
These functions distinguish between:
- the full built-in catalog
- the currently visible built-in subset
- the merged built-in + MCP pool

### Preservation requirement
A compatible rewrite must preserve:
- a stable built-in tool catalog boundary
- a mode/permission-sensitive visibility filter stage
- unified merging of built-in and MCP-provided tools
- stable ordering/dedup semantics for the prompt-visible tool pool
- the ability for special modes to restrict the visible tool set before exposure to the model

Detailed per-tool behaviors are documented separately in `docs/tool-contracts.md`.

---

## 6. Runtime task interfaces

## 6.1 Runtime task model
**File:** `src/Task.ts`

### Verified `TaskType`

```ts
export type TaskType =
  | 'local_bash'
  | 'local_agent'
  | 'remote_agent'
  | 'in_process_teammate'
  | 'local_workflow'
  | 'monitor_mcp'
  | 'dream'
```

### Verified `TaskStatus`

```ts
export type TaskStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'killed'
```

### Verified base state

```ts
export type TaskStateBase = {
  id: string
  type: TaskType
  status: TaskStatus
  description: string
  toolUseId?: string
  startTime: number
  endTime?: number
  totalPausedMs?: number
  outputFile: string
  outputOffset: number
  notified: boolean
}
```

### Verified runtime interface

```ts
export type Task = {
  name: string
  type: TaskType
  kill(taskId: string, setAppState: SetAppState): Promise<void>
}
```

### Preservation requirement
A rewrite must preserve:
- typed task kinds
- stable lifecycle status values
- per-task output file/state association
- lifecycle control by task ID
- app-state visibility of currently tracked tasks

---

## 6.2 Task registry
**File:** `src/tasks.ts`

Verified functions:

```ts
getAllTasks(): Task[]
getTaskByType(type: TaskType): Task | undefined
```

### Preservation requirement
A compatible rewrite must preserve a registry-based task lookup boundary so task implementations can be composed and feature-gated without hard-coding them into all callsites.

---

## 6.3 Terminal task-status helper
**File:** `src/Task.ts`

Verified rule:
- terminal statuses are `completed`, `failed`, `killed`

### Preservation requirement
A rewrite must preserve the existence of a terminal-status concept so routing/orchestration code can distinguish live tasks from finished ones.

---

## 7. File-backed persistent task-list interface

This section covers the persistent coordination/task-list layer, which is distinct from the runtime background task model above.

**File:** `src/utils/tasks.ts`

## 7.1 Persistent task schema

```ts
export type Task = {
  id: string
  subject: string
  description: string
  activeForm?: string
  owner?: string
  status: 'pending' | 'in_progress' | 'completed'
  blocks: string[]
  blockedBy: string[]
  metadata?: Record<string, unknown>
}
```

### Preservation requirement
A rewrite must preserve these semantic fields because they are the coordination surface used by task-oriented tools and teammate flows.

---

## 7.2 Core persistent task-list operations
Verified operations include:

```ts
resetTaskList(taskListId: string): Promise<void>
getTaskListId(): string
getTasksDir(taskListId: string): string
getTaskPath(taskListId: string, taskId: string): string
ensureTasksDir(taskListId: string): Promise<void>
createTask(taskListId: string, taskData: Omit<Task, 'id'>): Promise<string>
getTask(taskListId: string, taskId: string): Promise<Task | null>
updateTask(taskListId: string, taskId: string, updates: Partial<Omit<Task, 'id'>>): Promise<Task | null>
deleteTask(taskListId: string, taskId: string): Promise<boolean>
listTasks(taskListId: string): Promise<Task[]>
blockTask(taskListId: string, fromTaskId: string, toTaskId: string): Promise<boolean>
claimTask(taskListId: string, taskId: string, claimantAgentId: string, options?: ClaimTaskOptions): Promise<ClaimTaskResult>
getAgentStatuses(teamName: string): Promise<AgentStatus[] | null>
unassignTeammateTasks(...): Promise<UnassignTasksResult>
```

### Preservation requirement
A compatible rewrite must preserve the existence of these coordination operations, even if the storage backend changes.

If storage is migrated away from files, the replacement must still preserve:
- stable task-list identity per team/session context
- create/get/update/delete/list behavior
- dependency edges
- ownership claiming semantics
- teammate-status derivation capabilities
- teammate-unassignment operations

---

## 7.3 Persistent coordination semantics
Verified semantics from the implementation include:
- tasks are stored durably under a per-task-list directory
- task IDs are monotonically increasing numeric strings
- a high-water-mark file prevents ID reuse
- file locks are used for concurrency safety
- `claimTask()` includes atomic busy/ownership checks
- ownership and blocker graphs are part of the coordination model

### Preservation requirement
These semantics are part of the external coordination contract and must be preserved in behavior even if the backend changes:
- no task ID reuse after deletion/reset in a live logical task list
- atomic claim/create/update behavior
- durable ownership/blocking state shared across participants

Detailed task-tool behaviors built on top of this store are documented in `docs/tool-contracts.md`.

---

## 8. Multi-agent and backend interfaces

## 8.1 Backend type model
**File:** `src/utils/swarm/backends/types.ts`

### Verified types

```ts
export type BackendType = 'tmux' | 'iterm2' | 'in-process'
export type PaneBackendType = 'tmux' | 'iterm2'
```

### Preservation requirement
A rewrite must preserve the explicit distinction between:
- pane-backed execution/visualization backends
- in-process execution backends

The exact backend set may evolve, but the orchestration layer must still distinguish backend classes with materially different lifecycle and transport behavior.

---

## 8.2 `PaneBackend`
**File:** `src/utils/swarm/backends/types.ts`

Representative verified surface includes:

```ts
isAvailable(): Promise<boolean>
isRunningInside(): Promise<boolean>
createTeammatePaneInSwarmView(name, color): Promise<CreatePaneResult>
sendCommandToPane(paneId, command, useExternalSession?): Promise<void>
setPaneBorderColor(...): Promise<void>
setPaneTitle(...): Promise<void>
enablePaneBorderStatus(...): Promise<void>
rebalancePanes(windowTarget, hasLeader): Promise<void>
killPane(paneId, useExternalSession?): Promise<boolean>
hidePane(paneId, useExternalSession?): Promise<boolean>
showPane(paneId, targetWindowOrPane, useExternalSession?): Promise<boolean>
```

### Preservation requirement
A compatible rewrite must preserve a boundary between teammate orchestration and terminal-pane control operations.

That does not require tmux/iTerm2 forever, but it does require that pane operations remain encapsulated behind an adapter-like interface rather than leaking into orchestration code.

---

## 8.3 `TeammateExecutor`
**Files:** `src/utils/swarm/backends/types.ts`, `src/utils/swarm/backends/InProcessBackend.ts`

### Verified shape

```ts
export type TeammateExecutor = {
  readonly type: BackendType
  isAvailable(): Promise<boolean>
  spawn(config: TeammateSpawnConfig): Promise<TeammateSpawnResult>
  sendMessage(agentId: string, message: TeammateMessage): Promise<void>
  terminate(agentId: string, reason?: string): Promise<boolean>
  kill(agentId: string): Promise<boolean>
  isActive(agentId: string): Promise<boolean>
}
```

### Verified supporting types

```ts
export type TeammateSpawnConfig = {
  name: string
  teamName: string
  color?: AgentColorName
  planModeRequired?: boolean
  prompt: string
  cwd: string
  model?: string
  systemPrompt?: string
  systemPromptMode?: 'default' | 'replace' | 'append'
  worktreePath?: string
  parentSessionId: string
  permissions?: string[]
  allowPermissionPrompts?: boolean
}

export type TeammateSpawnResult = {
  success: boolean
  agentId: string
  error?: string
  abortController?: AbortController
  taskId?: string
  paneId?: PaneId
}

export type TeammateMessage = {
  text: string
  from: string
  color?: string
  timestamp?: string
  summary?: string
}
```

### Preservation requirement
A rewrite must preserve:
- backend-agnostic spawn/send/terminate/kill/isActive operations
- explicit teammate spawn configuration including identity, prompt, cwd, model, system-prompt mode, parent session, and permission settings
- spawn results that can carry backend-specific control handles while still exposing a stable common success/agent identity surface
- message-based communication rather than direct shared-object coupling

---

## 8.4 `InProcessBackend`
**File:** `src/utils/swarm/backends/InProcessBackend.ts`

### Verified semantics
- in-process teammates run in the same process
- they are logically isolated from the leader’s turn-local message state
- they still communicate through mailbox/message mechanisms
- they are registered in app state as tasks
- they are controlled through `AbortController`
- graceful termination uses a shutdown-request path; hard kill aborts immediately
- the backend requires a `ToolUseContext` to be set before `spawn()`:

```ts
setContext(context: ToolUseContext): void
```

### Preservation requirement
A compatible rewrite must preserve these behavioral distinctions:
- same-process execution does not imply direct shared-conversation-state mutation
- in-process workers remain app-state-visible and lifecycle-managed
- graceful terminate and hard kill remain distinct operations
- in-process execution still fits under the same message-oriented teammate executor abstraction

Detailed message-routing semantics are documented in `docs/tool-contracts.md` under `SendMessageTool`.

---

## 9. Relationship to lower-level contract docs

To avoid redundancy, the following lower-level interfaces are specified in other docs and are not repeated here in full.

### 9.1 Tool-level request/response contracts
For exact tool schemas and behaviors, see:
- `docs/tool-contracts.md`

This includes the detailed contracts for inspected tools such as:
- task-list tools
- web tools
- skill/tool search tools
- message/team tools
- cron tools
- file write/read behavior
- remote trigger tool

### 9.2 Remote HTTP endpoint contracts
For exact methods, paths, headers, payloads, retry rules, and response handling, see:
- `docs/remote-api.md`

This includes:
- sessions API
- environments API
- remote trigger API
- shared auth and retry behavior

---

## 10. Compatibility risks if these boundaries change

A rewrite that changes these boundaries without deliberate compatibility work risks:

1. **SDK/headless breakage**
   - if the conversation engine stops streaming turn events asynchronously

2. **Tool capability loss**
   - if tools are flattened into plain execute functions and lose validation/permissions/rendering/progress behavior

3. **Task/orchestration regressions**
   - if runtime tasks lose stable statuses or app-state visibility

4. **Team backend regressions**
   - if teammate backends no longer share a common lifecycle interface

5. **Coordination-store race conditions**
   - if persistent task-list locking and monotonic-ID semantics are removed without replacement

6. **Recovery regressions**
   - if tombstones, compact boundaries, or in-turn retries disappear from the event model

---

## 11. Rewrite guidance

### Keep stable or compatibility-wrap
- the conversation-engine construction boundary
- `submitMessage()`-style streamed turn submission
- `query()`-style streamed kernel boundary
- the compound `Tool` abstraction
- the capability surface currently carried by `ToolUseContext`
- the permission-context boundary
- runtime task typing and terminal-status semantics
- teammate executor spawn/send/terminate/kill/isActive surface
- persistent task-list coordination semantics

### Safe to refactor internally if behavior is preserved
- splitting `ToolUseContext` into smaller services
- replacing file-backed task storage with another durable backend
- replacing imperative query-loop internals with an explicit state machine
- replacing pane/in-process backend implementations while preserving the common executor boundary
- reorganizing startup/composition logic outside these runtime interfaces

---

## 12. Confidence and limits

High confidence:
- the interfaces and boundaries documented above were verified directly from the inspected source files
- the role of each boundary is supported by callsites and type signatures

Lower confidence:
- internal behaviors of modules not present in this snapshot
- lower-level semantics for tools whose implementation files were not inspected directly

Where more detailed verified contracts exist, this document intentionally defers to the more specific companion docs rather than restating them.
