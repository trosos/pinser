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
