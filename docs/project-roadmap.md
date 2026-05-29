# Project roadmap

This document proposes a staged roadmap for implementing Pinser.

It is meant to be a practical delivery aid for developers and architects. It complements the architecture documentation in `docs/architecture/` and the stack choice in `docs/implementation-stack-decision.md`.

The roadmap is intentionally phase-based rather than date-based.

## Normative use of this roadmap

Unless there is an explicit documented reason to do otherwise:

- work should proceed phase by phase
- each phase should have explicit completeness criteria before the next phase is treated as done
- later phases may begin experimentally before earlier phases are fully complete, but should not be declared stable until earlier phase criteria are met
- safety, persistence correctness, and tool correctness take precedence over UI polish and breadth features

## Guiding principles for sequencing

This roadmap follows the priorities already reflected in the architecture docs:

1. safety and correctness first
2. single-agent local usefulness second
3. persistence and recovery robustness third
4. coordination and ecosystem breadth after that

In practice, this means the project should optimize for:

- a safe local runtime before parity breadth
- a credible coding assistant before advanced orchestration
- explicit completeness gates rather than vague “mostly works” milestones

Deferred work should not be documented only as “out of scope”. Any intentionally deferred item that is expected to be implemented later should name its target phase in this roadmap.

## Phase 0: project foundation and bootstrap

### Objective

Create a minimal but disciplined Python project foundation that allows implementation to start without committing to premature architecture.

### Scope

- establish Python packaging and repository layout
- establish formatting, linting, and type-checking workflow
- establish test runner and basic CI expectations
- define base package/module layout aligned with the implementation stack decision
- create initial configuration loading skeleton

### Deliverables

- Python project metadata and dependency management setup
- initial `src/` package layout
- baseline `pytest`, `ruff`, and type checker configuration
- a minimal CLI entrypoint that starts and exits successfully
- contributor-facing notes for local setup if needed

Current status: Phase 0 bootstrap has started. The repository now contains a minimal Python package layout, a Typer CLI entrypoint, and initial configuration/test/tooling setup.

### Completeness criteria

Phase 0 is complete when all of the following are true:

- the repository can be set up from scratch using the chosen Python workflow
- linting, formatting, tests, and type checking can all be run locally with documented commands
- CI or an equivalent local script enforces those checks
- the project contains a valid importable `pinser` package
- a basic CLI command runs successfully without placeholder crashes
- the chosen runtime baseline and quality tools match `docs/implementation-stack-decision.md`

### Out of scope

- model integration
- interactive runtime behavior
- tool execution logic
- persistence semantics beyond configuration bootstrap

## Phase 1: runtime skeleton and event model

### Objective

Build the first usable shape of the conversation runtime kernel without yet implementing the full tool and persistence surface.

### Scope

- define core session and turn abstractions
- define the internal event model for user, assistant, progress, and tool-related events
- define the async streaming protocol between runtime and CLI/headless callers
- define message normalization and prompt assembly skeletons
- define model provider abstraction and a minimal mock or test backend

### Deliverables

- typed runtime interfaces for session state, turn execution, and emitted events
- async generator-based turn execution skeleton
- prompt/context assembly interfaces
- model adapter abstraction with at least one fake/test implementation
- tests for event ordering and basic turn lifecycle behavior

### Completeness criteria

Phase 1 is complete when all of the following are true:

- one conversation/session object can accept a user submission and stream typed events back to a caller
- the turn loop is implemented as an async streaming workflow rather than a one-shot call
- cancellation is represented in the design and tested at least in a basic form
- the runtime has a documented distinction between session state and turn-local state
- event types are defined clearly enough to support persistence later without redesigning everything
- tests demonstrate deterministic behavior for a minimal no-tool turn

### Recommended stopping point

A sensible Phase 1 stopping point is reached when the runtime has:

- typed session state
- typed turn state
- a headless runtime facade
- async streaming turn execution
- cancellation tests
- prompt assembly abstraction
- a fake model backend
- an event model with explicit separation between:
  - conversation content events
  - lifecycle/progress events

This stopping point is intentionally short of persistence and real tool execution. It gives Phase 3 transcript work and Phase 2 tool work a stable runtime boundary without prematurely committing to storage or tool semantics.

### Out of scope

- real shell/file tools
- real persistence and resume
- advanced retry/fallback behavior
- remote APIs

## Phase 2: core local tools and permission engine

See also: [`docs/phase2/scope.md`](./phase2/scope.md) for the implementation-scoping note that distinguishes minimum required Phase 2 work from deferred compatibility hardening.

See also: [`docs/phase2.1/scope.md`](./phase2.1/scope.md) for the immediate post-Phase-2 hardening checkpoint covering validation consistency, path and special-file hardening, output budgeting, untrusted tool-output framing, and minimal Bash isolation improvements.

### Objective

Make the system useful as a local coding assistant by implementing the core tool surface and safety rules.

### Scope

- implement `Read`, `Edit`, `FileWrite`, `Glob`, and `Grep`
- implement Bash execution with a safety model; PowerShell is optional and deferred
- implement the initial permission engine and approval modes
- implement filesystem/path safety checks
- enforce read-before-write and stale-read protections

### Deliverables

- working file tools with typed inputs and outputs
- working shell execution tool with permission enforcement
- policy engine for allow/deny/ask behavior
- path validation and workspace boundary checks
- tests for safety-sensitive cases and permission decisions

### Completeness criteria

Phase 2 is complete when all of the following are true:

- the core file tools work end-to-end in normal local workflows
- file mutation paths enforce read-before-write constraints
- path handling prevents obvious traversal and workspace-boundary violations
- shell execution is routed through explicit permission decisions
- approval modes are externally visible and tested
- unsafe cases fail clearly rather than silently degrading
- the project has integration tests covering representative file and shell workflows

### Out of scope

- notebook editing; Phase 2 should fail clearly rather than provide notebook-safe mutation
- MCP integration
- multi-agent delegation
- remote execution
- user-visible background shell task identity and lifecycle

## Phase 3: transcript persistence, resume, and recovery basics

### Objective

Make the runtime durable enough to support session continuation and recovery after interruption.

### Scope

- implement transcript persistence model
- separate prompt history from transcript persistence
- persist user input early enough for resume correctness
- implement basic session reload/resume behavior
- implement initial recovery and transcript repair semantics
- continue the separation between transcript storage, tool-result records, and prompt-normalization inputs so Phase 2.1 untrusted tool-output framing can evolve into replay-safe persistence semantics

### Deliverables

- persistent transcript/session storage
- durable prompt history store separated from transcript store
- resume command or equivalent session continuation path
- tests for reload after interruption
- initial tombstone or equivalent repair mechanism for interrupted/partial output

### Completeness criteria

Phase 3 is complete when all of the following are true:

- a session can be interrupted and resumed without losing committed user input
- transcript state can be reconstructed from persisted records
- prompt history and durable transcript persistence are implemented as separate concerns
- partial or interrupted turn artifacts are handled by a defined recovery mechanism
- the runtime can reload at least one real persisted session in tests
- persistence behavior is documented enough that future compaction work has a stable base

### Out of scope

- full compaction strategy
- advanced sidechains
- remote session persistence

## Phase 4: model routing, retries, and daily-driver robustness

### Objective

Upgrade the runtime from a prototype into a credible day-to-day local assistant.

### Scope

- implement configurable model selection
- implement runtime effective model choice and fallback model support
- implement same-turn retry and failure handling semantics
- implement result budgeting and tool result shaping
- improve cancellation, interruption, and output consistency
- add `LSP` if available and important for target users

### Deliverables

- model routing service with preferred/effective/fallback distinctions
- retry/failure state handling for common runtime failures
- more robust terminal interaction behavior
- optional LSP integration layer
- stronger integration tests around retries and cancellation

### Deferred from earlier phases

This phase also absorbs specific work intentionally excluded earlier:

- from Phase 2: PowerShell execution support, if cross-platform parity remains a product goal
- from Phase 2: richer permission-mode completeness such as `acceptEdits`, `plan`, `auto`, and related approval hardening
- from Phase 2.1: richer permission-decision metadata, layered whole-tool policy evaluation, argv-first Bash execution for shell-free commands with auto-allow limited to policy-approved program/argument patterns, and stronger policy defaults for network-capable or side-effect-heavy commands

### Completeness criteria

Phase 4 is complete when all of the following are true:

- the runtime can distinguish configured model choice from effective runtime model choice
- same-turn fallback or retry works for at least the targeted failure classes
- cancellation during active turns leaves transcript state consistent
- tool result volume is controlled well enough to avoid obvious transcript bloat
- at least one realistic end-to-end local coding workflow is reliable enough for repeated developer use
- if LSP is included in scope, it has typed contracts and at least basic integration coverage

### Out of scope

- team/swarm orchestration
- remote bridge operation
- scheduling/cron

## Phase 5: compaction, long-session maintenance, and recovery hardening

### Objective

Support long-lived sessions without transcript growth or recovery complexity making the runtime fragile.

### Scope

- implement session compaction/checkpointing strategy
- implement recovery flows around compacted sessions
- improve transcript repair semantics
- harden replay boundaries and crash consistency
- strengthen replay/poisoning defenses that depend on compaction, reconstruction, and recovery boundaries

### Deliverables

- compaction/checkpointing design implemented in code
- recovery paths that work across compacted and uncompacted sessions
- tests for replay after compaction and interruption
- documentation of reconstruction boundaries and guarantees

### Completeness criteria

Phase 5 is complete when all of the following are true:

- long sessions can be compacted without breaking future continuation
- recovery after compaction is tested and repeatable
- transcript reconstruction has explicit correctness boundaries
- interrupted work around compaction does not leave the session irreparably inconsistent
- the persistence model remains understandable rather than becoming a set of ad hoc patches

### Out of scope

- multi-agent orchestration at scale
- remote session parity

## Phase 6: tasks, background work, and single-user coordination

### Objective

Support the first level of delegated and long-running work beyond the foreground turn loop.

### Scope

- implement background task lifecycle and tracking
- implement task stop/kill/output retrieval behavior
- return to shell safety for background execution, including task identity, output continuity, and permission enforcement
- implement a durable task store if needed for local coordination
- provide typed task interfaces to CLI/headless callers

### Deliverables

- background task manager
- output retrieval and status inspection
- stop/terminate behavior
- tests for long-running subprocess-backed work

### Deferred from earlier phases

This phase also absorbs specific work intentionally excluded earlier:

- from Phase 2: user-visible background shell task identity and lifecycle
- from Phase 2: detached/background shell output continuity and retrieval semantics
- from Phase 2: permission enforcement rules for detached/background shell execution

### Completeness criteria

Phase 6 is complete when all of the following are true:

- a user can start, inspect, and stop background work reliably
- task identity and output retrieval semantics are stable and tested
- task state survives the intended persistence boundary for the phase
- background execution does not compromise shell safety or permission enforcement
- the feature is useful for real local workflows rather than being only an internal abstraction

### Out of scope

- full team/swarm coordination
- remote workers
- mailbox-based multi-agent messaging

## Phase 7: teams, delegation, and coordinated worker execution

### Objective

Introduce multi-agent and coordination behavior once the single-agent runtime is stable.

### Scope

- implement durable shared task coordination where needed
- implement worker lifecycle abstraction for in-process/local delegated workers
- implement agent messaging primitives
- implement first team/delegation workflows

### Deliverables

- worker/backend abstraction
- messaging/control plane for delegated workers
- durable shared task coordination model
- tests for at least one delegation workflow

### Completeness criteria

Phase 7 is complete when all of the following are true:

- at least one delegated worker flow works end-to-end with clear lifecycle control
- worker communication is explicit rather than hidden in shared mutable state
- shared task coordination semantics are durable enough for resume/reload where intended
- failure or cancellation of delegated work is visible and recoverable
- the orchestration layer is backend-oriented rather than scattered through the runtime

### Out of scope

- premium remote environment parity
- scheduled recurring work

## Phase 8: MCP and ecosystem integrations

### Objective

Add external capability integration after the built-in local runtime is solid.

### Scope

- implement MCP tool participation in the tool catalog
- implement MCP resource listing/reading
- implement server authentication flow where needed
- integrate dynamic tool discovery into runtime/tool filtering

### Deliverables

- MCP integration layer
- resource and tool bridging support
- auth/config hooks for MCP servers
- tests using at least one representative MCP integration path

### Completeness criteria

Phase 8 is complete when all of the following are true:

- MCP tools can be discovered, surfaced, and invoked through the same runtime tool path used by built-ins where appropriate
- resource listing/reading semantics are implemented and tested
- authentication and configuration behavior are explicit rather than magic
- failures in external integrations degrade clearly and do not destabilize the core runtime

### Out of scope

- remote session bridge parity unless coupled intentionally to this phase

## Phase 9: remote/API-backed operation

### Objective

Support remote or bridge-backed use cases after the local product is credible.

### Scope

- implement remote session and API surfaces
- implement bridge/session lifecycle behavior
- normalize messages and events for remote transport
- separate remote transport concerns from core runtime concerns

### Deliverables

- API server or remote adapter layer
- typed request/response models
- remote session lifecycle handling
- tests for at least one remote session flow

### Completeness criteria

Phase 9 is complete when all of the following are true:

- a remote client can create or attach to a session through a defined API
- message/event normalization for transport is stable and tested
- remote lifecycle events are explicit and recoverable
- the local runtime remains usable without the remote layer
- remote behavior is implemented as an adapter around the runtime, not as a forked second architecture

### Out of scope

- enterprise-scale deployment concerns unless explicitly targeted

## Phase 10: UX refinement, optional surfaces, and release hardening

### Objective

Turn the implementation into a polished release candidate.

### Scope

- improve CLI/TUI ergonomics
- add notebook support if needed
- improve packaging, release workflow, and docs
- fill targeted compatibility gaps that matter for users
- improve performance hot spots discovered in real use

### Deliverables

- release checklist
- packaging/install docs
- compatibility notes and documented limitations
- optional richer TUI or notebook support if justified

### Deferred from earlier phases

This phase also absorbs specific work intentionally excluded earlier:

- from Phase 2: notebook-safe editing and mutation support, if still justified by real usage
- from Phase 2: managed-policy, migration-completeness, and enterprise-style permission compatibility work, if still justified
- from earlier phases generally: compatibility polish intentionally omitted to keep core phases small and safe
- from Phase 2.1 and later phases: any remaining managed-policy, migration, or enterprise-style permission compatibility gaps that are not needed for the core local runtime

### Completeness criteria

Phase 10 is complete when all of the following are true:

- the project can be installed and used by a new developer without ad hoc setup help
- the supported feature set and known limitations are documented clearly
- targeted UX rough edges have been addressed without compromising the runtime model
- release processes are repeatable
- remaining gaps are conscious product decisions rather than unknown implementation holes

## Cross-phase definition of done

A phase should not be called complete just because code exists. In general, each phase should satisfy all of the following:

- the scope is documented
- the main interfaces are typed
- the behavior is covered by tests proportionate to the risk
- failure behavior is defined, not accidental
- the feature integrates into the main runtime rather than living as a disconnected experiment
- important constraints from the architecture docs are preserved

## Suggested checkpoint labels

If shorter labels are useful in planning, the phases above map roughly to these checkpoints:

- **Checkpoint A:** Phases 0–2 — safe single-agent prototype
- **Checkpoint B:** Phases 3–5 — durable daily-driver local assistant
- **Checkpoint C:** Phases 6–7 — delegated and coordinated workflows
- **Checkpoint D:** Phases 8–10 — ecosystem breadth, remote operation, and release hardening

## Bottom line

The roadmap should bias the project toward a safe, typed, local-first Python implementation that becomes useful early, then durable, then broad.

The key discipline is to treat completeness criteria as real gates, especially for:

- permission safety
- file mutation safety
- transcript durability
- cancellation and recovery behavior
- separation between core runtime and optional ecosystem layers
