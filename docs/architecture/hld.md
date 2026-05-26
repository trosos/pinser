# High-level architecture for rewrite planning

This document describes the verified high-level runtime architecture of the codebase and frames it for clean-room rewrite planning.

It focuses on:
- major runtime layers
- conversation execution flow
- multi-agent orchestration structure
- model-routing structure
- asynchronous execution patterns
- rewrite-relevant architectural invariants

It is intentionally high-level.
For lower-level preservation details, use:
- `docs/interfaces-and-endpoints.md` for major runtime boundaries and interfaces
- `docs/tool-contracts.md` for per-tool contracts
- `docs/remote-api.md` for HTTP endpoint contracts

Primary inspected files for this architecture view:
- `src/main.tsx`
- `src/context.ts`
- `src/commands.ts`
- `src/tools.ts`
- `src/tasks.ts`
- `src/QueryEngine.ts`
- `src/query.ts`
- `src/Task.ts`
- `src/history.ts`

Where deeper imported implementations were not present in the workspace snapshot, this document stays at the level of verified callsites, types, orchestration behavior, and clearly-labeled inference.

---

## 1. Executive summary

This codebase is a **stateful agent runtime** wrapped in CLI/TUI and headless adapters.
Its core architectural pattern is:

1. bootstrap the process, mode, capabilities, and session context
2. construct registries for commands, tools, tasks, and agent/team facilities
3. create one conversation engine per conversation
4. run each user submission through a recursive async turn loop
5. stream model output, execute tools, update persistence, and continue until termination

This is not a simple request/response chatbot.
It is a multi-mode orchestration runtime supporting:
- interactive CLI/TUI sessions
- headless/SDK sessions
- background tasks
- local and remote agents
- coordinator/team flows
- remote session and MCP integration

The strongest architectural characteristics are:
- **async event streaming as the core execution protocol**
- **tool execution as part of the main turn loop**
- **registry-based capability composition**
- **explicit but dispersed support for multi-agent execution**
- **runtime model selection and fallback**
- **latency-sensitive startup and background prefetching**

For a rewrite, the key design opportunity is not to change the external behavior, but to re-separate the current monolithic orchestration into cleaner layers with sharper interfaces.

---

## 2. Top-level runtime layers

## 2.1 Bootstrap and composition layer
**Key file:** `src/main.tsx`

`main.tsx` is the top-level composition root.
It currently combines several architectural roles:
- process bootstrapper
- environment/setup hardening layer
- CLI/mode router
- dependency assembler
- session launcher

### Verified responsibilities
It handles or initiates:
- settings and startup policy loading
- mode selection
- trust/auth/client detection
- command/tool/task registry assembly
- MCP setup and prefetch
- prompt/model/thinking configuration
- worktree/assistant/remote/SSH/REPL/headless routing
- final launch into interactive or headless execution

### Architectural takeaway
There is already a conceptual split between:
- **critical-path startup**
- **deferred background warmup**

A rewrite should preserve that split explicitly rather than as ad hoc latency optimizations inside one file.

---

## 2.2 Context assembly layer
**Key file:** `src/context.ts`

This layer gathers and memoizes prompt-relevant environment state.

### Verified context families
- **system context**: environment/worktree/git-style context and related runtime facts
- **user context**: CLAUDE.md/memory-like content, date, extra directories, and mode-gated additions

### Architectural role
This is a context-provider layer that feeds prompt construction and classifier/model context.

### Rewrite invariant
A rewrite must preserve:
- context assembly as a distinct stage from turn execution
- separate system-context and user-context providers
- memoization/prefetchability where safe
- trust-sensitive gating for context sources that touch the filesystem or shell

---

## 2.3 Capability registry layer
This layer is spread across:
- `src/commands.ts`
- `src/tools.ts`
- `src/tasks.ts`

### Commands
The command registry is assembled from multiple sources, including built-ins and dynamically discovered skills/workflows/plugins.

Architecturally, this is a **capability discovery and filtering layer**.

### Tools
The tool registry builds a built-in catalog, filters it by mode/permissions/environment, and merges it with MCP-provided tools.

Architecturally, this is a **tool capability compiler**.

### Tasks
The task registry defines the supported background/delegated execution kinds.

Architecturally, this is a **background execution catalog**.

### Rewrite invariant
A rewrite must preserve registry-based composition rather than hard-coding capabilities directly into the main loop.

---

## 2.4 Conversation engine layer
This layer is primarily:
- `src/QueryEngine.ts`
- `src/query.ts`

### `QueryEngine`
Owns session-local mutable conversation state and coordinates submission-level behavior.

### `query()` / query loop
Owns per-turn execution, model/tool recursion, retries, compaction, and termination.

### Architectural role
Together they form the **conversation runtime kernel**:
- `QueryEngine` = per-conversation/session boundary
- `query()` = per-turn execution boundary

### Rewrite invariant
A rewrite must preserve this conceptual split even if the implementation is reorganized.

---

## 2.5 Persistence layer
Primary observed files and callsites:
- `src/history.ts`
- transcript/session helpers referenced from `QueryEngine.ts` and `main.tsx`

### Distinct persistence surfaces
The current architecture distinguishes between:
- **prompt history** for UX/history recall
- **conversation transcript/session persistence** for resume/replay
- **file-backed team task lists** for shared coordination

### Rewrite invariant
These are different persistence responsibilities and should remain separate.
Collapsing them into one generic store would weaken both correctness and operability.

---

## 3. End-to-end execution flow

## 3.1 Session startup flow
At a high level, startup does the following:

1. initialize process and startup policies
2. determine mode/client/session routing
3. load settings and startup prerequisites
4. assemble tools, commands, tasks, context providers, permissions, and integrations
5. initialize or preinitialize external capability providers such as MCP
6. launch either:
   - interactive REPL/TUI flow, or
   - headless/SDK flow

### Architectural meaning
Startup is a **session composition pipeline**.
It is not part of the turn loop itself.

### Rewrite invariant
A rewrite should make session composition explicit and separate it from the conversation kernel.

---

## 3.2 Headless/SDK conversation flow
In headless usage, the architecture is approximately:

1. assemble session config and app state
2. create a `QueryEngine`
3. call `submitMessage()` for each user submission
4. stream SDK-visible events from the engine
5. let the engine persist transcript/session state across submissions

### Architectural meaning
The headless API is not just “call the model.”
It is “submit one user turn into a stateful session runtime and stream the resulting execution events.”

### Rewrite invariant
Preserve this sessionful streamed interaction model.

---

## 3.3 One turn inside the engine
A single turn submission expands into roughly this flow:

1. accept user input
2. normalize/process user input and slash-command effects
3. assemble prompt layers and contexts
4. persist enough state for resumability
5. enter the query loop
6. stream assistant output
7. execute emitted tool calls
8. append tool results and continue loop iterations as needed
9. terminate with a final turn result

### Architectural meaning
The turn is a recursive workflow, not a single model request.

### Rewrite invariant
The external turn API must continue to hide this recursion from callers.

---

## 4. Conversation execution architecture

## 4.1 Conversation state model
The runtime uses multiple overlapping state scopes.

### Session-local conversation state
Owned by `QueryEngine`.
This is the durable in-memory state for the current conversation across multiple submissions.

### Turn-local working state
Owned by `query()` / the query loop.
This is the mutable working set for the current recursive turn execution.

### App/global session state
Accessed via `getAppState` / `setAppState`.
This includes shared runtime facilities such as tasks, MCP state, permission context, team context, and other session-wide services.

### Persisted transcript/session state
Used for resume/replay and crash consistency.

### Rewrite invariant
A rewrite should preserve these distinct scopes instead of conflating all state into either global app state or local turn state.

---

## 4.2 Event-rich transcript model
The runtime operates on more than just user/assistant chat messages.
Verified event/message families include assistant, user, system, progress, stream events, tool-use summaries, attachments, and tombstones.

### Architectural meaning
The system behaves more like an event-sourced conversation runtime than a plain chat transcript.

### Rewrite invariant
The event model must preserve:
- canonical transcript entries
- ephemeral transport/UI events
- recovery/repair events
- structural events such as compact boundaries

More specific interface detail is in `docs/interfaces-and-endpoints.md`.

---

## 4.3 Query loop as the runtime kernel
`query.ts` is the behavioral core of the agent cycle.
Its responsibilities include:
- preparing messages and context
- selecting the runtime model
- streaming model output
- handling fallback/retry/recovery
- executing tools
- deciding continuation vs termination

### Architectural meaning
This is effectively a finite-state conversational workflow, currently implemented imperatively.

### Rewrite invariant
A rewrite may convert this to an explicit state machine, but must preserve:
- the same phase structure
- in-turn retries/recoveries
- mixed event streaming
- tool-use continuation loop

---

## 5. Multi-agent orchestration architecture

This area is only partially inspectable from the snapshot, but enough structure is visible to describe the architecture.

## 5.1 Multiple execution entities exist
Verified evidence shows the runtime supports at least these execution entities:
- main conversation agent
- local background agent task
- remote agent task
- in-process teammate
- pane-backed teammate/backend flows
- team/swarm contexts
- coordinator/delegation-oriented flows

### Architectural meaning
The runtime is designed to support multi-agent execution across multiple execution media, not just subroutines inside one agent.

---

## 5.2 Two broad orchestration styles

### In-process teammate/team execution
Evidence includes in-process teammate task types, backend abstractions, and team/message tools.

Architecturally, this is a **same-process but logically isolated worker model**.

### Out-of-process or remote execution
Evidence includes local agent tasks, remote agent tasks, pane backends, and remote session routing.

Architecturally, this is a **task-/process-/transport-backed worker model**.

### Rewrite invariant
A rewrite should preserve these as separate backends behind a common orchestration interface rather than collapsing them into special cases everywhere.

---

## 5.3 Message-oriented coordination
Agent/team coordination is visibly message-oriented.
Observed evidence includes:
- teammate executors with `sendMessage(...)`
- team messaging tools
- mailbox semantics in inspected tool contracts
- shutdown and approval-style coordination flows

### Architectural meaning
Coordination is not just shared mutable memory; it is a communication plane layered over execution backends.

### Rewrite invariant
A rewrite should preserve explicit agent/team messaging semantics across backends.

---

## 5.4 Team-scoped durable coordination
The file-backed persistent task list is used as a coordination surface for teams and teammates.

### Architectural meaning
There are two different but related coordination mechanisms:
- live agent/backend control and messaging
- durable shared task ownership/blocking state

### Rewrite invariant
A rewrite must preserve both layers:
- live execution orchestration
- durable shared work coordination

---

## 6. Model-routing architecture

## 6.1 Model selection is layered
Model selection is not a single startup constant.
It is influenced by:
- user/config/env-provided preferred model
- session-level overrides
- runtime mode/policy
- context-size and runtime conditions
- fallback behavior during failure handling

### Architectural meaning
This is a layered routing system rather than a fixed model choice.

### Rewrite invariant
A rewrite should preserve the distinction between:
- configured/preferred main model
- runtime effective model for a given iteration
- fallback model used after a failure condition

---

## 6.2 Runtime fallback is in-turn failover
The query loop handles model fallback inside the same logical turn by clearing partial state, switching model, and retrying.

### Architectural meaning
Fallback is a recovery mechanism inside the conversation runtime, not a caller-managed retry strategy.

### Rewrite invariant
Preserve:
- same-turn failover
- repair/tombstoning of partial outputs where needed
- continuity of the logical turn despite model replacement

---

## 6.3 Multi-model roles exist
Even in the inspected snapshot, the system clearly has multiple model roles, not just one:
- main loop model
- fallback model
- advisor-like specialized model
- lightweight summarization/support models implied by tool-use summary behavior and related orchestration

### Rewrite guidance
A clean-room rewrite should formalize a model-routing service with explicit roles rather than scattering model-role logic across startup and turn execution.

---

## 7. Asynchronous architecture

## 7.1 Async generators are the core protocol
Both the session-level and turn-level execution boundaries are async generators.

### Architectural meaning
Streaming is the native execution model.
The runtime does not compute a whole answer and then emit it afterward.

### Rewrite invariant
Keep async event streaming as the core engine protocol.
This is one of the strongest architectural choices in the current system.

---

## 7.2 Structured but informal concurrency
The code repeatedly uses:
- parallel startup work
- opportunistic background prefetch
- fire-and-forget background tasks where latency matters
- awaited flushes where durability matters
- abort controllers for cancellation domains

### Architectural meaning
The architecture already uses structured concurrency concepts, though mostly informally.

### Rewrite guidance
A rewrite should make concurrency domains explicit, such as:
- startup task group
- per-turn task group
- post-turn background task group
- cancellation scopes

---

## 7.3 Cancellation is a first-class concern
Cancellation is visible in the engine and in tool/task execution.
The system explicitly handles interruption during streaming and tool execution while trying to preserve transcript consistency.

### Rewrite invariant
Every turn remains cancellable, but cancellation must preserve transcript/tool consistency rather than leaving half-applied runtime artifacts.

---

## 7.4 Background work is hidden under active latency
The codebase repeatedly overlaps non-critical work under model/tool latency.
Examples include context/memory/skill discovery prefetch and asynchronous summary generation.

### Architectural meaning
The runtime is optimized for perceived responsiveness, not just raw correctness.

### Rewrite invariant
A rewrite should preserve the distinction between:
- correctness-critical awaited work
- opportunistic prefetch/background work

---

## 8. Architectural strengths

The current architecture has several strong properties worth preserving:

### 8.1 Strong central execution loop
The system has a clear behavioral center in the query loop, even if surrounding composition is messy.

### 8.2 Good streaming abstraction
Async generators are a good fit for the mixed stream of assistant output, tools, progress, and transport events.

### 8.3 Thoughtful failure recovery
The runtime visibly handles:
- fallback model retry
- prompt/size recovery
- partial-output repair
- transcript consistency maintenance

### 8.4 Registry-based capability composition
Commands, tools, and tasks are composed through registries instead of being baked directly into the core loop.

### 8.5 Real latency awareness
Startup and runtime flows are already designed around responsiveness and deferred work.

---

## 9. Architectural pain points and rewrite targets

## 9.1 Oversized composition root
`main.tsx` mixes too many responsibilities and should be decomposed in a rewrite.

## 9.2 Over-broad runtime dependency bags
`ToolUseContext` carries too many concerns and should likely be split into smaller service interfaces.

## 9.3 Dispersed mode logic
Mode-specific behavior is spread across startup, tool filtering, prompt assembly, and execution paths.
A rewrite should consolidate this into explicit policies/strategies.

## 9.4 Query loop mixes multiple concerns
The query loop currently combines:
- context preparation
- runtime model selection
- streaming orchestration
- retry/recovery
- tool execution
- budget enforcement
- stop conditions

A rewrite should keep the behavior but re-separate the stages.

## 9.5 Multi-agent abstractions are present but scattered
The system already supports multiple execution backends and coordination patterns, but the abstractions are spread across tasks, tools, backends, and startup state.

---

## 10. Recommended rewrite architecture

This section is a design recommendation, not a statement of current implementation.

## 10.1 Suggested top-level modules

### A. Runtime kernel
Owns:
- turn state machine
- event emission
- retries/recovery
- cancellation
- budgets and stop conditions

### B. Prompt/context engine
Owns:
- system prompt composition
- user/system context gathering
- mode overlays
- memory overlays
- model-visible message preparation

### C. Tool execution plane
Owns:
- tool registry
- availability filtering
- permission evaluation
- tool execution
- tool result normalization
- MCP tool integration

### D. Agent orchestration plane
Owns:
- agent identities
- team/swarm/coordinator semantics
- backend abstraction for in-process/local/remote workers
- agent messaging and lifecycle control

### E. Persistence layer
Owns:
- transcript/session persistence
- prompt history
- durable coordination/task-list persistence

### F. Transport adapters
Owns:
- CLI/TUI projection
- headless/SDK streaming projection
- remote/bridge viewers or other frontends

### G. Startup/composition layer
Owns:
- CLI parsing
- settings/auth/trust setup
- dependency assembly
- mode selection

---

## 10.2 Suggested execution phases for the conversation kernel
A rewrite could formalize these phases explicitly:

1. AcceptInput
2. NormalizeInput
3. PersistUserInput
4. PrepareContext
5. PrepareMessages
6. CallModel
7. StreamAssistantOutput
8. ExecuteTools
9. ApplyAuxiliaryUpdates
10. EvaluateStopConditions
11. DecideContinuation
12. EmitTerminalResult

Recovery branches include:
- fallback model retry
- compaction retry
- max-output retry/escalation
- abort
- terminal failure

### Rewrite note
This is already largely implicit in the current query loop.
Formalizing it would improve maintainability without changing the external behavior.

---

## 10.3 Suggested multi-agent abstraction shape
A rewrite should preserve the common orchestration interface across execution backends.
Conceptually, the system wants an abstraction like:
- spawn worker
- send message to worker
- terminate worker gracefully
- kill worker forcefully
- inspect liveness/status

The exact interface names can vary, but the backend-neutral orchestration boundary should remain.

---

## 10.4 Suggested model-routing abstraction
A rewrite should preserve multi-role model routing but centralize it behind one service responsible for:
- main model selection
- runtime effective model selection
- fallback routing
- specialized model-role selection

---

## 11. Verified architecture summary by topic

## Multi-agent orchestration
Verified at the architecture level:
- multiple execution backends/entities exist
- team/message/task coordination exists
- in-process and non-in-process execution are both supported
- teammate identity and lifecycle are first-class concerns

## Model routing
Verified at the architecture level:
- model routing is layered and runtime-sensitive
- fallback is handled inside the turn loop
- multiple model roles are implied or explicit

## Async architecture
Verified at the architecture level:
- startup and runtime use extensive async overlap
- event streaming is core to execution
- tool execution is interleaved with assistant turns
- cancellation and durability tradeoffs are explicit

---

## 12. Confidence and limits

High confidence:
- overall runtime layering
- conversation engine / query loop split
- event-stream architecture
- registry-based capability composition
- model fallback as an in-turn behavior
- presence of multi-agent backend abstractions
- separation of prompt history, transcript persistence, and durable task coordination

Lower confidence:
- deeper coordinator/swarm internals not visible in this snapshot
- imported implementation details for modules absent from the workspace
- precise lower-level behavior of non-inspected tools and services

Where lower-level verified contracts exist, this document intentionally avoids restating them and instead relies on the dedicated companion docs.
