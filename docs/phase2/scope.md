# Phase 2 scope and implementation note

This document narrows Phase 2 into an implementation-ready local scope for Pinser.

It complements, and does not replace:

- [`docs/project-roadmap.md`](../project-roadmap.md)
- [`docs/architecture/permission-engine.md`](../architecture/permission-engine.md)
- [`docs/architecture/path-and-filesystem-safety.md`](../architecture/path-and-filesystem-safety.md)
- [`docs/architecture/bash-and-powershell-safety.md`](../architecture/bash-and-powershell-safety.md)
- [`docs/architecture/tool-contracts.md`](../architecture/tool-contracts.md)

The large architecture documents remain the normative compatibility references. This file exists to make Phase 2 execution small enough, explicit enough, and consistent enough to implement without re-deciding scope in every PR.

## Implementation-shaping note

Phase 2 should stay narrow in scope, but should not paint the implementation into a corner.

Even in a conservative first Phase 2 slice, the implementation should preserve extension points for:

- tool-specific permission hooks
- structured permission decisions such as `allow`, `ask`, and `deny`, while leaving room for an internal `passthrough`-style result later if needed
- event categories that can later support transcript persistence and recovery work
- future additional permission modes, even if only `default` and `dontAsk` are active in the first Phase 2 implementation

The goal is to keep Phase 2 reviewable and safety-first without prematurely collapsing interfaces that later phases are expected to extend.

## Purpose

Phase 2 should make Pinser useful as a local coding assistant while keeping the implementation narrow enough to review and verify.

This note explicitly distinguishes:

- the **minimum required Phase 2 implementation**
- **compatibility extras deferred to later hardening**

It also records a few planning decisions so contributors do not have to infer them from several architecture documents.

## Phase 2 platform decision

For Phase 2:

- **Bash is required**
- **PowerShell is optional and deferred**

This means the first complete Phase 2 target is a Bash-first local implementation that works well on the current Python runtime and preserves the documented safety invariants that matter most for local coding workflows.

PowerShell is still part of the long-term compatibility direction and remains documented in the architecture references, but it is not required to call Phase 2 complete.

Suggested later landing point for PowerShell work:

- begin in **Phase 4** if needed for daily-driver robustness on Windows-like workflows
- otherwise keep it available as post-Phase-4 compatibility work before release hardening

## Phase 2 minimum required implementation

Phase 2 minimum scope is the smallest implementation that should be allowed to count as Phase 2 complete.

### Required tools

Implement these built-in tools end to end:

- `Read`
- `Edit`
- `FileWrite`
- `Glob`
- `Grep`
- `Bash`

### Required tool behavior

The minimum implementation should preserve these behavior classes:

- typed tool inputs and outputs
- workspace-aware path validation
- read-before-write enforcement for file mutation
- stale-read protection for file mutation
- safe failure for blocked mutation paths
- safe failure for obvious workspace-boundary violations
- normal tool execution through the Phase 1 runtime event stream

### Required filesystem and safety behavior

The minimum implementation should preserve these core safety invariants:

- absolute-path handling for file tools where required by the documented contracts
- workspace boundary enforcement
- path traversal resistance
- protected-path checks for clearly sensitive internal/config paths
- read-before-write requires a prior full read
- partial reads do not authorize mutation
- stale-read checks run immediately before mutation
- UNC/network-path handling and other dangerous-path checks should fail closed or force approval rather than silently probing unsafely

### Required Bash behavior

The minimum Phase 2 Bash implementation should preserve the Bash-first essentials needed for safe local usefulness:

- explicit command execution tool with typed inputs
- permission-gated execution
- whole-tool and content-sensitive command permission matching
- deny/ask precedence over broad allow behavior
- argument-sensitive read-only classification sufficient for common local workflows
- path/redirection validation for obvious write targets
- compound-command handling sufficient to avoid trivial piggybacking of dangerous subcommands
- a clear distinction between sandboxed and unsandboxed execution paths when sandbox support exists

Phase 2 does **not** need to implement the full shell compatibility surface described in the architecture docs as long as the omitted parts are documented explicitly and the implemented subset remains conservative.

### Required permission engine behavior

The minimum Phase 2 permission engine should preserve:

- explicit decisions: `allow`, `deny`, `ask`
- whole-tool rules and content-sensitive rules
- tool-specific permission checking hooks
- `dontAsk` behavior that converts final asks into denies
- conservative default behavior for unresolved sensitive actions
- explicit user-visible approval modes
- clear denied vs approval-required outcomes

### Required testing

Phase 2 should include tests for at least:

- normal file read and edit workflows
- read-before-write rejection
- stale-read rejection
- workspace/path boundary rejection
- representative Bash allow/deny/ask behavior
- permission mode behavior for at least the implemented modes
- runtime integration tests that show tool execution flowing through the Phase 1 event model

## Permission engine Phase 2 implementation scope

The architecture documentation for permissions is broader than what Phase 2 needs in its first complete implementation. For Phase 2, use the following split.

### Required in Phase 2

Implement at minimum:

- explicit `allow` / `deny` / `ask`
- whole-tool vs content-sensitive rules
- source-aware enough rule handling to support the initial runtime and future extension cleanly
- tool-specific permission-check hooks
- `dontAsk`
- a default interactive mode
- a constrained bypass mode only if it can preserve the bypass-immune safety invariants already documented
- clear reasoned denial/ask messages for file and Bash workflows
- path-sensitive checks and file-mutation safety checks

### Deferred from Phase 2 to later hardening

Do not treat the following as required to call Phase 2 complete, but keep them in mind when shaping the implementation:

- full `acceptEdits`, `plan`, and `auto` mode semantics
- dangerous-rule stripping/restoration for auto mode
- classifier-mediated approval flows and denial tracking
- full managed-policy and multi-source permission persistence behavior
- richer permission update algebra and on-disk editing flows
- plan-mode restoration edge cases
- full headless hook-before-deny behavior
- broader legacy alias migration coverage

Suggested later landing points:

- **Phase 4**: `acceptEdits`, retry-adjacent permission hardening, daily-driver approval ergonomics, PowerShell if needed
- **Phase 6**: background-task-aware shell permission integration
- **Phase 10** or targeted compatibility hardening before release: classifier-heavy, managed-policy, and migration-completeness work if still needed

## Notebook editing decision

Notebook editing is **out of scope for Phase 2**.

This phase should treat notebook editing as deferred work, not scaffold-required work.

Implications:

- `NotebookEdit` is not required in Phase 2
- generic `Edit` should not silently claim notebook support
- if notebook files are encountered, the implementation should fail clearly rather than pretending notebook-safe mutation exists

Suggested later landing point:

- **Phase 10** if notebook support remains optional
- or earlier only if a concrete user need justifies promoting it into an active phase

## Shell backgrounding decision

Background shell task identity is **Phase 6 only**.

For Phase 2:

- user-visible background task lifecycle is out of scope
- stable shell task identity/output retrieval is out of scope
- Phase 2 Bash should focus on foreground execution and safety

This keeps Phase 2 aligned with the roadmap distinction between core local tools and later background task orchestration.

## Architecture and documentation follow-up tasks

The following follow-up tasks should be tracked during or immediately after Phase 2 implementation. They do **not** require changing the large architecture documents unless future understanding changes.

### Architecture note task: Phase 2 tool/runtime implementation note

Add a short implementation note under `docs/phase2/` documenting:

- Python tool interface shape
- permission-check hook shape
- event emission expectations for tool execution
- how tool results attach to the existing Phase 1 event model
- the expected Phase 2 turn shape for tool-using turns, including the model -> permission check -> tool execution -> tool result -> continued model response flow

This should be a small local document. It does **not** require editing the large architecture reference docs.

The broader architecture already discusses turns, tool results, retries, and recovery in several places, but extracting the Phase 2 turn shape into one local implementation note should reduce ambiguity for contributors landing the first tool loop.

Suggested landing point:

- add during the first Phase 2 tool-integration PR, or before merging the first real tool runner

### Contributor note task: CLI output expectations for tool and safety flows

Add a short contributor note under `docs/phase2/` documenting expected CLI output for:

- tool running
- permission required
- denied by policy
- stale read blocked
- read-before-write blocked

This should remain lightweight and should complement, not replace, `docs/ui-design-contract.md`.

Suggested landing point:

- add once the first real tool execution reaches the CLI, before output patterns spread informally

### Documentation task: omitted functionality register

Add a short document under `docs/phase2/` listing important functionality intentionally omitted from the first Phase 2 implementation.

Purpose:

- make later planning easier
- reduce accidental scope drift
- help contributors decide whether a requested change is Phase 2 work or later hardening

This omitted-functionality note should be concise and point back to the architecture docs for deeper detail.

Suggested landing point:

- create before declaring Phase 2 complete

## Deferred functionality and suggested roadmap placement

The following Phase 2-adjacent extras are intentionally deferred and should be planned in later phases.

### Better permission-mode completeness

Examples:

- `acceptEdits`
- `plan`
- `auto`
- auto-mode dangerous-rule stripping/restoration
- classifier integration

Suggested roadmap placement:

- primarily **Phase 4**

### PowerShell compatibility

Examples:

- PowerShell command execution
- PowerShell-specific parser and provider-path safety
- Windows mandatory-sandbox policy behavior

Suggested roadmap placement:

- **Phase 4**, or post-Phase-4 compatibility hardening if not needed earlier

### Background shell lifecycle integration

Examples:

- background shell task IDs
- output retrieval
- stop/kill behavior
- shell safety review for background execution semantics

Suggested roadmap placement:

- **Phase 6**

### Notebook-aware mutation

Examples:

- `NotebookEdit`
- notebook-specific read-before-write semantics
- cell-aware notebook edits

Suggested roadmap placement:

- **Phase 10** unless reprioritized by user need

### Policy and enterprise-style permission completeness

Examples:

- managed-rules-only behavior
- multi-source persistence editing flows
- broader migration and alias coverage

Suggested roadmap placement:

- **Phase 10** or later compatibility hardening before release

## Deferred item landing zones

The following items are intentionally excluded from Phase 2 and should be picked up in the roadmap phases named here:

- PowerShell execution support -> **Phase 4**
- richer permission-mode completeness such as `acceptEdits`, `plan`, `auto`, and related hardening -> **Phase 4**
- user-visible background shell task identity and lifecycle -> **Phase 6**
- detached/background shell output continuity and permission semantics -> **Phase 6**
- notebook-safe editing support -> **Phase 10** if still justified
- managed-policy, migration-completeness, and enterprise-style permission compatibility work -> **Phase 10** if still justified

## Brief execution plan

A sensible execution plan for Phase 2 is:

1. **Define local implementation notes and runtime integration shape**
   - add the short `docs/phase2/` implementation note
   - document the expected Phase 2 turn shape for tool-using turns
   - implement the Python tool interface and runtime hook points

2. **Define CLI/runtime presentation expectations early**
   - add the small CLI-output note under `docs/phase2/`
   - make tool-running, permission, denial, and file-safety output expectations explicit before they spread informally

3. **Land safe read-only tooling first**
   - implement `Read`, `Glob`, and `Grep`
   - establish path validation and workspace-scope checks

4. **Land the initial permission engine slice**
   - implement allow/deny/ask
   - add whole-tool and content-sensitive matching
   - add `dontAsk`
   - keep unresolved cases conservative

5. **Land mutation tooling with file safety invariants**
   - implement `Edit` and `FileWrite`
   - enforce full-read and stale-read protections

6. **Land Bash foreground execution**
   - implement the Bash tool with permission gating and a conservative safety subset
   - verify clear failure behavior for denied and approval-required commands

7. **Stabilize integration tests and close documentation gaps**
   - add integration tests covering file and Bash workflows through the event stream
   - add the omitted-functionality note before declaring Phase 2 complete

## Bottom line

Phase 2 should produce a Bash-first, local-first, safety-first tool layer on top of the Phase 1 runtime.

The main discipline is to keep the implementation conservative, document what is intentionally omitted, and defer compatibility breadth to later phases rather than partially and opaquely expanding Phase 2.