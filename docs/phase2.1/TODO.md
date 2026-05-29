# Phase 2.1 implementation plan

This file records the implementation plan for Phase 2.1 based on the current scope note, architecture documentation, threat model, and tools security assessment.

Primary references reviewed:

- `docs/phase2.1/scope.md`
- `docs/phase2/scope.md`
- `docs/project-roadmap.md`
- `docs/architecture/permission-engine.md`
- `docs/architecture/path-and-filesystem-safety.md`
- `docs/architecture/bash-and-powershell-safety.md`
- `docs/architecture/tool-contracts.md`
- `docs/architecture/tool-result-budgeting-and-dedup.md`
- `docs/architecture/implementation-notes-and-gotchas.md`
- `docs/threat-model.md`
- `docs/tools-security-assessment.md`

## Goal

Implement the narrow hardening checkpoint defined by Phase 2.1 without drifting into larger redesign work that belongs to later roadmap phases.

The target outcome is:

- consistent typed validation failures
- stronger shared path and special-file safety
- bounded tool outputs
- explicit prompt-facing framing of tool output as untrusted data
- safer Bash subprocess behavior

## Scope discipline

Phase 2.1 should strengthen the current Phase 2 implementation, not redesign it.

Do now:

- validation consistency
- shared path-policy hardening
- output budgeting for current local tools
- explicit tool-result rendering/framing
- minimal Bash isolation and timeout cleanup hardening

Do not expand into later-phase work here:

- full transcript/persistence redesign
- broad permission-engine redesign
- richer approval mode semantics
- full argv-vs-shell Bash redesign
- background shell lifecycle support
- PowerShell parity work

## Implementation clarification notes

These notes resolve the main places where `docs/phase2.1/scope.md` is intentionally simplified relative to the architecture docs.

### 1. Validation before permission evaluation does not mean unsafe probing before permission gates

We should add an explicit validation step before permission evaluation and execution, but validation must remain safe.

In practice this means:

- schema/argument validation should happen before permission evaluation
- permission and path-safety decisions should operate on validated input objects
- validation must not perform unsafe filesystem probing on UNC/network-like paths or other suspicious inputs before permission gating
- some path-safety checks remain part of the permission/safety layer rather than generic argument parsing

Implementation rule:

- validate shape and scalar constraints first
- keep risky filesystem interaction behind the shared path-safety layer

### 2. Centralized path policy must preserve defense in depth

The architecture docs favor shared filesystem safety semantics, but they also explicitly rely on layered checks for safety-sensitive cases.

Implementation rule:

- centralize policy definition and common helpers
- do not remove tool-local guardrails that intentionally prevent unsafe probing or shell-specific bypasses
- preserve layered UNC/network hardening and shell/path-specific checks where they provide defense in depth

### 3. Explicit tool-result rendering must preserve tool-result closure and contract semantics

Phase 2.1 should replace raw prompt-facing use of arbitrary tool output with explicit rendering, but that should not break the broader tool-result architecture.

Implementation rule:

- preserve explicit `tool_use` -> `tool_result` closure semantics
- keep one normalized model-facing tool-result rendering path
- preserve required result semantics for current tools while making the prompt-facing representation labeled and bounded
- do not collapse execution metadata and model-visible content into the same unchecked field

### 4. Bash environment minimization must be conservative and test-backed

The security assessment correctly calls inherited environment a risk, but aggressive scrubbing can break normal workflows if done carelessly.

Implementation rule:

- minimize environment inheritance by default
- preserve only clearly necessary variables
- add tests to verify reduced inheritance and still-functional normal execution
- avoid speculative platform abstractions in this phase

### 5. Phase 2.1 should improve Bash hardening without claiming shell-model completeness

The architecture docs describe a much broader shell model than Phase 2.1 can land.

Implementation rule:

- harden the current Bash path materially
- defer larger shell redesign items to later phases as documented
- avoid introducing partial backgrounding or half-complete shell-exec splits in this checkpoint

## Proposed execution order

### 1. Audit current implementation and map code touch points

First, inspect the current code paths for:

- tool validation and argument parsing
- session/runtime tool invocation flow
- permission evaluation entry points
- path safety helpers and per-tool path checks
- tool result rendering and prompt assembly
- Bash subprocess launch, timeout handling, and environment passing
- existing tests covering the above

Deliverable:

- a concrete file-level change map before editing behavior

### 1a. File-by-file implementation map

This audit maps the current implementation touchpoints to the planned Phase 2.1 work.

#### Core runtime flow

- `src/pinser/runtime/engine/session.py`
  - Current role:
    - orchestrates tool invocation lifecycle
    - builds permission requests
    - evaluates permission decisions
    - executes tools
    - emits tool started/completed/denied/blocked/failed events
    - appends `ToolResultMessage` into transcript
    - currently renders prompt-facing tool output through `_render_tool_result_message()`
  - Why it matters for Phase 2.1:
    - this is the main place to add an explicit validation-before-permission step if done at runtime level
    - this is the main place to stop relying on raw `output["content"]`
    - this is where prompt-facing result closure behavior must remain coherent
  - Likely changes:
    - introduce validated invocation handling or explicit validation call before `build_permission_request()` / `decide_permission()` / `execute()`
    - replace `_render_tool_result_message()` with an explicit, bounded, tool-result rendering path
    - keep denied/blocked/failed transcript insertion behavior stable while improving labeling
  - Main risks:
    - duplicating transcript entries accidentally
    - changing current event ordering
    - mixing runtime metadata with model-visible text

- `src/pinser/runtime/context/prompt.py`
  - Current role:
    - maps transcript items into prompt messages
    - currently passes `ToolResultMessage.content` directly as tool-role prompt content
  - Why it matters for Phase 2.1:
    - prompt-facing untrusted tool-output framing lands here or very near here
  - Likely changes:
    - add explicit labeling/framing for `ToolResultMessage`
    - ensure tool outputs are visibly untrusted and bounded
  - Main risks:
    - changing existing tests that assert raw tool content
    - introducing formatting that obscures useful tool output too much

- `src/pinser/runtime/conversation/messages.py`
  - Current role:
    - defines transcript item types, including `ToolResultMessage(tool_name, content, is_error)`
  - Why it matters for Phase 2.1:
    - if prompt-facing rendering needs more structured stored metadata, this is the smallest place to extend transcript shape
  - Likely changes:
    - possibly add minimal metadata needed for labeled/bounded rendering
    - or leave shape unchanged if rendering can be derived from current fields plus runtime changes
  - Main risks:
    - making Phase 2.1 over-architected
    - broad test fallout if message shape changes unnecessarily

#### Tool contract and errors

- `src/pinser/runtime/tools/protocol.py`
  - Current role:
    - defines `ToolInvocation`, `ToolExecutionResult`, and minimal `Tool` protocol
  - Why it matters for Phase 2.1:
    - current contract has no explicit validation hook or model-visible renderer
  - Likely changes:
    - add a narrow validation method and/or explicit prompt-render method to the tool contract if needed
    - keep scope tight and avoid full typed-input redesign in this phase
  - Main risks:
    - forcing a larger architecture shift than Phase 2.1 requires

- `src/pinser/runtime/tools_errors.py`
  - Current role:
    - defines `ToolExecutionError`, `ToolSafetyBlockedError`, and `ToolArgumentError`
  - Why it matters for Phase 2.1:
    - target error type for validation cleanup already exists here
  - Likely changes:
    - probably no or minimal code changes
    - may gain more precise docstrings or stay unchanged

#### Permissions and events

- `src/pinser/runtime/permissions/models.py`
  - Current role:
    - defines `PermissionDecisionKind`, `PermissionDecision`, and `PermissionRequest`
  - Why it matters for Phase 2.1:
    - if we add machine-readable reason fields later, this is the location
    - Phase 2.1 may or may not actually need schema changes here depending on implementation choices
  - Likely changes:
    - maybe none for the first implementation pass
    - possibly small metadata additions if needed for clearer reason handling
  - Main risks:
    - widening scope into broader permission-engine redesign

- `src/pinser/runtime/events/models.py`
  - Current role:
    - defines tool lifecycle events and current event payloads
  - Why it matters for Phase 2.1:
    - event coverage must remain stable if validation and rendering paths change
  - Likely changes:
    - probably none in the first pass
    - maybe small additions only if required by implementation
  - Main risks:
    - unnecessary event-schema churn

#### Shared filesystem safety and mutation tracking

- `src/pinser/runtime/safety.py`
  - Current role:
    - defines `PathSafety`, `PathSafetyDecision`, and `ResolvedPath`
    - currently handles workspace containment, network-like path detection, blocked read devices, and top-level protected write paths
  - Why it matters for Phase 2.1:
    - this is the primary landing zone for shared path hardening
  - Likely changes:
    - add lexical path checks before filesystem interaction
    - centralize protected-path policy more cleanly
    - add non-regular-file detection helpers
    - possibly add reusable helpers for read/write/search-specific checks
  - Main risks:
    - probing filesystem state too early for suspicious inputs
    - breaking legitimate relative path handling
    - platform-specific assumptions around special files

- `src/pinser/runtime/engine/file_state.py`
  - Current role:
    - tracks read/write observations and enforces read-before-write / stale-read safety
  - Why it matters for Phase 2.1:
    - path-hardening changes may need corresponding normalization updates here
    - stale-read/write critical section behavior should remain intact during write-path changes
  - Likely changes:
    - possibly route normalization through improved shared path helpers
    - maybe add or adjust tests rather than major code changes
  - Main risks:
    - changing path normalization keys in a way that breaks overwrite protection

#### File and search tools

- `src/pinser/runtime/tools/read.py`
  - Current role:
    - validates path with a plain `ValueError`
    - checks read permission through `PathSafety`
    - reads full file content with no output budget
    - records reads in `FileStateTracker`
  - Why it matters for Phase 2.1:
    - direct target for typed validation cleanup, file-size/output caps, and special-file enforcement
  - Likely changes:
    - replace `ValueError` with `ToolArgumentError`
    - use hardened path policy helpers
    - add regular-file checks and size/output cap behavior
    - return truncation metadata and safer rendered content path
  - Main risks:
    - breaking current read-before-write behavior
    - changing exact content expectations in prompt-related tests

- `src/pinser/runtime/tools/write.py`
  - Current role:
    - already uses `ToolArgumentError`
    - relies on `PathSafety.check_write_path()` and direct `PathSafety.resolve()`
    - writes exact full content and emits diff metadata
  - Why it matters for Phase 2.1:
    - needs shared path hardening and non-regular-file protection
  - Likely changes:
    - adopt improved path-policy helpers
    - reject non-regular existing targets
    - preserve current read-before-write and stale-read semantics
  - Main risks:
    - accidentally weakening overwrite safety while refactoring path checks

- `src/pinser/runtime/tools/edit.py`
  - Current role:
    - already uses `ToolArgumentError`
    - relies on write-path safety and file-state checks
    - edits exact text and emits diff metadata
  - Why it matters for Phase 2.1:
    - needs the same hardened shared path and special-file behavior as `Write`
  - Likely changes:
    - adopt improved shared path-policy helpers
    - reject non-regular targets clearly
    - preserve notebook guard and overwrite invariants
  - Main risks:
    - regressions in exact-match edit semantics

- `src/pinser/runtime/tools/glob.py`
  - Current role:
    - validates pattern with a plain `ValueError`
    - traverses with `workspace_root.glob(pattern)`
    - filters candidates back through `PathSafety.resolve()`
    - has no traversal or result budget
  - Why it matters for Phase 2.1:
    - direct target for typed validation cleanup and output budgeting
    - likely needs tighter shared path normalization use
  - Likely changes:
    - replace `ValueError` with `ToolArgumentError`
    - add traversal/result caps and truncation metadata
    - possibly add safer pattern validation constraints if needed
  - Main risks:
    - over-constraining useful glob patterns
    - performance changes from additional filtering

- `src/pinser/runtime/tools/grep.py`
  - Current role:
    - validates inputs with plain `ValueError`
    - compiles arbitrary regex with `re.compile()`
    - walks files via `glob`/`rglob`
    - reads full files line-by-line with no file-size or output budget
  - Why it matters for Phase 2.1:
    - direct target for typed validation cleanup, search budgeting, and shared file-safety rules
  - Likely changes:
    - replace `ValueError` with `ToolArgumentError`
    - add traversal/file/result/output caps
    - skip or block oversized/non-regular inputs consistently through shared safety helpers
    - return truncation metadata
  - Main risks:
    - broad test changes due to summary/count behavior
    - regex cost remains partially open unless explicitly constrained

#### Bash tool

- `src/pinser/runtime/tools/bash.py`
  - Current role:
    - validates arguments with `ToolArgumentError`
    - analyzes commands heuristically for allow/ask/deny
    - executes via `/bin/bash -lc <command>`
    - inherits ambient environment
    - uses `process.kill()` on timeout
    - returns full stdout/stderr with no size caps
  - Why it matters for Phase 2.1:
    - this is the Bash hardening landing zone
  - Likely changes:
    - add explicit environment minimization
    - launch in its own process group/session for full descendant cleanup
    - kill full process group on timeout
    - add stdout/stderr caps and truncation metadata
    - keep current shell model otherwise narrowly scoped
  - Main risks:
    - environment scrubbing breaking tests or expected shell startup behavior
    - timeout cleanup becoming flaky in tests
    - accidental behavioral drift in permission analysis while editing execution path

#### Tool wiring

- `src/pinser/runtime/tools/__init__.py`
- `src/pinser/runtime/tools/registry.py`
  - Current role:
    - expose and register tools
  - Why they matter for Phase 2.1:
    - only if contract changes require registry or export updates
  - Likely changes:
    - none or very small supporting edits

#### Primary tests to update or extend

- `tests/test_safety.py`
  - Main landing zone for lexical traversal, network-path, protected-path, symlink escape, and special-file coverage

- `tests/test_tool_result_messages.py`
  - Main landing zone for prompt-facing tool-result framing expectations

- `tests/test_session_tools.py`
  - Main landing zone for runtime-level validation/failure behavior and model-visible tool-result expectations

- `tests/test_bash_tool.py`
  - Main landing zone for Bash output caps, timeout cleanup, and environment minimization

- `tests/test_glob_tool.py`
- `tests/test_grep_tool.py`
- `tests/test_write_tool.py`
- `tests/test_edit_tool.py`
- `tests/test_file_state.py`
  - Supporting landing zones for per-tool behavior and overwrite-safety invariants

### 1b. Suggested implementation sequence based on actual code layout

1. Start in `src/pinser/runtime/tools/read.py`, `glob.py`, and `grep.py` for typed validation cleanup.
2. Then harden `src/pinser/runtime/safety.py` and adapt `read.py`, `write.py`, `edit.py`, `glob.py`, and `grep.py` to use the shared policy consistently.
3. Then update `src/pinser/runtime/engine/session.py` and `src/pinser/runtime/context/prompt.py` for explicit bounded tool-result rendering and untrusted framing.
4. Then harden `src/pinser/runtime/tools/bash.py`.
5. Keep `tests/test_session_tools.py`, `tests/test_tool_result_messages.py`, `tests/test_safety.py`, and `tests/test_bash_tool.py` in lockstep with each step.

### 2. Validation and typed-failure cleanup

Implement:

- replace remaining plain `ValueError` argument failures with `ToolArgumentError`
- add or tighten an explicit validation step before permission evaluation and execution
- ensure permission checks receive validated input rather than ad hoc raw mappings where feasible in current architecture
- add tests proving validation failures surface as typed, predictable runtime failures

Expected acceptance:

- invalid tool arguments fail consistently with typed errors
- validation happens before tool execution
- session-level tests show stable validation failure behavior

### 3. Shared path-policy hardening

Implement:

- a shared path-safety entry point used by file and search tools where applicable
- dual lexical-path and resolved-path checks
- centralized protected-path policy
- explicit rejection of existing non-regular files for read/write operations
- explicit symlink escape coverage for reads and writes
- preservation of UNC/network fail-closed behavior before unsafe probing

Expected acceptance:

- traversal attempts are rejected clearly
- symlink escapes are rejected clearly
- protected paths are denied consistently
- device/FIFO/socket targets are denied where testable

### 4. Output budgeting across current local tools

Implement:

- `Read` output/file-size policy
- `Glob` traversal and result-count budgets
- `Grep` traversal, file-count, match-count, and/or output-size budgets
- `Bash` stdout/stderr caps
- clear truncation and budget indicators in structured results and rendered output

Expected acceptance:

- oversized outputs do not flow unbounded into prompt context
- truncation is visible and testable
- output caps do not break normal small-result workflows

### 5. Prompt-facing tool-result rendering and untrusted framing

Implement:

- explicit tool-result rendering rather than prompt-facing reliance on arbitrary raw `output["content"]`
- prompt assembly framing that labels tool output as tool-produced, untrusted data
- bounded rendering built on the output-budgeting work above
- tests proving labeled, bounded prompt-facing tool output

Expected acceptance:

- prompt context receives labeled tool output
- model-facing output is not raw unchecked tool payload
- result closure and runtime event behavior remain coherent

### 6. Bash isolation and timeout-cleanup hardening

Implement:

- subprocess environment minimization by default
- process-group cleanup on timeout
- integration of Bash output caps if not already complete from step 4
- regression tests for timeout cleanup and reduced environment inheritance

Expected acceptance:

- timed-out commands do not leave descendant processes running as intended by implementation
- Bash no longer inherits the full ambient environment by default
- normal foreground Bash execution remains functional

### 7. Close-out verification pass

Finish with:

- integration tests covering representative file and Bash workflows through the runtime event path
- review of any intentionally deferred work against roadmap landing zones
- documentation updates if user-visible behavior or limits changed materially

## Detailed work checklist

### A. Validation and tool contract consistency

- [ ] Identify every remaining plain `ValueError` used for tool argument failures
- [ ] Replace those with `ToolArgumentError`
- [ ] Confirm session/runtime handling preserves typed failure surfaces
- [ ] Add an explicit validation step before permission evaluation/execution
- [ ] Ensure validation does not perform unsafe filesystem probing
- [ ] Add tests for invalid `Read` arguments
- [ ] Add tests for invalid `Glob` arguments
- [ ] Add tests for invalid `Grep` arguments
- [ ] Add tests for invalid `Bash` arguments if needed
- [ ] Add session-level tests for typed validation failures

### B. Shared path-safety hardening

- [ ] Identify current path-safety helpers and embedded per-tool checks
- [ ] Add shared lexical-path safety checks
- [ ] Add/shared resolved-path containment checks
- [ ] Centralize protected-path policy definition
- [ ] Ensure protected-path checks remain case-insensitive where required by architecture
- [ ] Block existing non-regular files for reads
- [ ] Block existing non-regular files for writes
- [ ] Preserve UNC/network-path fail-closed behavior before unsafe probing
- [ ] Add tests for traversal variants
- [ ] Add tests for network-style path variants
- [ ] Add tests for symlink-inside-workspace -> outside-workspace escapes
- [ ] Add tests for protected-path denials
- [ ] Add tests for FIFO/socket/device denials where testable

### C. Output budgeting and result shaping

- [ ] Decide concrete budgets for `Read`, `Glob`, `Grep`, and `Bash`
- [ ] Implement `Read` size/output cap
- [ ] Implement `Glob` traversal/result cap
- [ ] Implement `Grep` traversal/result/output cap
- [ ] Implement `Bash` stdout/stderr cap
- [ ] Include truncation/budget metadata in tool results
- [ ] Add tests for oversized `Read`
- [ ] Add tests for oversized `Glob` result sets
- [ ] Add tests for oversized `Grep` result sets
- [ ] Add tests for oversized Bash stdout/stderr

### D. Prompt-facing untrusted tool-output framing

- [ ] Find current model-facing tool-result render path(s)
- [ ] Replace implicit raw prompt-facing rendering with explicit renderer
- [ ] Label model-facing tool output as tool-produced, untrusted content
- [ ] Ensure bounded output is used in rendered prompt-facing content
- [ ] Preserve coherent `tool_use`/`tool_result` pairing behavior
- [ ] Add tests that prompt-facing tool output is labeled
- [ ] Add tests that prompt-facing tool output is bounded

### E. Bash hardening

- [ ] Audit current subprocess launch environment
- [ ] Define minimal inherited environment policy
- [ ] Launch Bash in a process group/session suitable for descendant cleanup
- [ ] Kill the full process group on timeout
- [ ] Confirm output caps interact correctly with timeout/error paths
- [ ] Add regression tests for descendant cleanup on timeout
- [ ] Add regression tests for reduced environment inheritance

### F. Verification and close-out

- [ ] Run targeted tests during each step
- [ ] Run full verification after implementation
- [ ] Review behavior against `docs/phase2.1/scope.md` completeness criteria
- [ ] Check that no deferred Phase 3/4 work was accidentally pulled into scope
- [ ] Update docs if new limits/messages are user-visible

## Threat-focused test additions

At minimum, add or expand tests for:

- validation failures surfacing as `ToolArgumentError`
- symlink inside workspace resolving outside workspace
- write or read attempts against non-regular files in workspace where testable
- traversal and network-path variants rejected clearly
- protected-path denials remaining enforced
- oversized `Read` results truncated or blocked per policy
- `Glob` and `Grep` enforcing traversal/result budgets
- prompt-facing tool output labeled as untrusted
- `Bash` timeout cleanup removing subprocess trees as intended
- `Bash` default environment exposure reduced relative to the parent process

## Constraints to preserve while implementing

- keep changes tightly scoped to Phase 2.1
- preserve the current Phase 2 runtime/event model
- preserve file mutation invariants: read-before-write and stale-read checks
- preserve defense in depth for path safety and shell/path validation
- preserve normalized tool-result closure semantics
- do not add speculative abstractions beyond what is needed for this hardening checkpoint

## Definition of done for this plan

This plan is complete when the implementation satisfies all of the following:

- remaining argument-validation failures in current local tools surface as `ToolArgumentError`
- permission evaluation and execution operate on validated tool input
- path handling rejects lexical traversal and resolved out-of-workspace escapes
- existing non-regular files are rejected clearly for read/write operations
- representative tests cover symlink escapes, protected paths, and special-file denials where testable
- `Read`, `Glob`, `Grep`, and `Bash` produce bounded model-visible output with truncation or budget signaling
- prompt-facing tool output is labeled as tool-produced, untrusted content
- timed-out Bash executions clean up descendant processes as intended by the implementation
- Bash does not inherit the full ambient environment by default
