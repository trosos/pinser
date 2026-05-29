# Phase 2 implementation TODO and notes

Created while reviewing the repository on 2026-05-24.

For canonical project phase status, see [`docs/project-roadmap.md`](../project-roadmap.md).

## What exists today

- Phase 1 runtime skeleton is in place:
  - `Session` with in-memory transcript and async event streaming
  - event types: turn started, user message, progress, assistant message, turn completed, turn cancelled
  - fake model backend only
  - CLI can bootstrap and run a simple no-tool turn
- Settings are still minimal:
  - workspace root
  - `.pinser` state directory
- No real tool system yet
- No permission engine yet
- No persistence yet

## Phase 2 sources reviewed

Primary planning sources:

- `docs/project-roadmap.md`
- `docs/phase2/scope.md`
- `docs/architecture/INDEX.md`
- `docs/architecture/feature-prioritization.md`
- `docs/architecture/interfaces-and-endpoints.md`
- `docs/architecture/tool-contracts.md`
- `docs/architecture/permission-engine.md`
- `docs/architecture/path-and-filesystem-safety.md`
- `docs/architecture/bash-and-powershell-safety.md`
- `docs/architecture/transcript-and-persistence-semantics.md`

## Phase 2 minimum scope distilled

Required built-in tools:

- `Read`
- `Edit`
- `FileWrite`
- `Glob`
- `Grep`
- `Bash`

Required safety/permission behavior:

- typed tool inputs and outputs
- workspace-aware path validation
- workspace boundary enforcement
- path traversal resistance
- protected-path checks for clearly sensitive internal/config paths
- read-before-write enforcement for mutation
- partial reads must not authorize mutation
- stale-read protection immediately before mutation
- explicit permission decisions: `allow`, `deny`, `ask`
- whole-tool and content-sensitive rules
- `dontAsk` mode converts asks to denies
- conservative default behavior for sensitive unresolved actions
- Bash permission gating and deny/ask precedence over broad allow behavior
- clear user-visible failure modes

Explicitly deferred from Phase 2:

- PowerShell
- notebook editing
- background shell task lifecycle
- richer permission modes (`acceptEdits`, `plan`, `auto`)
- MCP
- remote execution
- multi-agent orchestration

## Architecture observations that matter for implementation

### Runtime/event model

Current event model is too narrow for Phase 2 tool turns. We will likely need new events for at least:

- tool-call started / running
- permission required
- tool denied
- tool result
- tool error / tool failed

Need to preserve the distinction already established in docs:

- durable conversation content vs ephemeral progress
- avoid designing tool progress/events in a way that will block Phase 3 transcript semantics

### Tool system shape

Architecture docs strongly suggest a first-class tool abstraction, not ad-hoc branching in session code.
A Phase 2-friendly Python shape should likely include:

- stable tool name
- input validation
- output type/result type
- permission hook
- execution function
- model-visible rendering helper if needed

### Permissions

Need layered permission evaluation, not a single monolithic check:

- global engine for whole-tool rules and modes
- tool-specific permission checks for file/shell semantics
- final normalized decision: allow / ask / deny

For first slice, only active external modes need to be:

- `default`
- `dontAsk`

But interfaces should leave room for later modes.

### File safety

Must build a reusable path safety layer before implementing mutation tools.
Likely responsibilities:

- normalize/resolve paths safely
- compare containment via normalized relative semantics, not string prefix
- fail closed on UNC/network-looking paths
- dual-check original and resolved paths where possible
- protect internal/config-sensitive paths
- distinguish partial read vs full read authorization
- store read snapshots for stale-read checks

### Bash safety

Phase 2 only needs conservative Bash foreground execution.
Do not overbuild background lifecycle now.
Minimum important pieces:

- explicit typed Bash input
- permission-gated execution path
- whole-tool rules and command-sensitive rules
- deny/ask precedence over allow
- read-only classification for common safe commands
- conservative validation for obvious writes/redirections/compound commands
- optional sandbox-routing shape should leave room for future implementation even if initial sandbox support is thin

## Proposed implementation order

1. Add local Phase 2 docs requested by `docs/phase2/scope.md`
   - implementation note for tool/runtime integration
   - CLI output expectations note
2. Introduce core Phase 2 runtime abstractions
   - tool protocol/registry
   - permission decision models
   - tool execution events
3. Implement shared filesystem/path safety utilities
4. Implement read-only tools first
   - `Read`
   - `Glob`
   - `Grep`
5. Implement initial permission engine
   - rule model
   - mode model (`default`, `dontAsk`)
   - whole-tool/content-sensitive evaluation hooks
6. Implement mutation tools with read tracking
   - `Edit`
   - `FileWrite`
7. Implement Bash foreground execution with conservative permission checks
8. Extend CLI/runtime integration tests for tool flows and safety failures
9. Add omitted-functionality register before declaring Phase 2 done

## Likely code areas to create

- `src/pinser/runtime/tools/`
- `src/pinser/runtime/permissions/`
- `src/pinser/runtime/filesystem/` or similar shared safety module
- possibly model/tool-loop support in `src/pinser/runtime/engine/`

## Open design questions before coding

- How will the model request tool usage in Phase 2?
  - deterministic fake backend emitting tool requests?
  - explicit test backend for tool loops?
- Should CLI expose approval mode now via option/config, or only internal default + `dontAsk` first?
- What exact protected-path set should Phase 2 enforce immediately for this repo shape?
- What minimum read snapshot metadata is enough for stale-read protection?
  - full contents hash?
  - mtime + size is probably not strong enough alone

## Acceptance checklist for Phase 2

- file tools work end-to-end in tests
- mutation requires prior full read
- stale writes are blocked
- workspace boundary violations fail clearly
- Bash runs only after explicit permission decision
- `dontAsk` converts approval-required Bash/file actions into denials
- integration tests exercise tool execution through runtime event stream
- Phase 2 docs added under `docs/phase2/`
