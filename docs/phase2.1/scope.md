# Phase 2.1 scope and hardening note

This document defines the immediate follow-up hardening work that should land after the initial Phase 2 implementation and before the project treats the local tools layer as a stable base for later roadmap phases.

For canonical project phase status, see [`docs/project-roadmap.md`](../project-roadmap.md).

It complements, and does not replace:

- [`docs/project-roadmap.md`](../project-roadmap.md)
- [`docs/phase2/scope.md`](../phase2/scope.md)
- [`docs/tools-security-assessment.md`](../tools-security-assessment.md)
- [`docs/threat-model.md`](../threat-model.md)
- the architecture references already linked from `docs/phase2/scope.md`

## Purpose

Phase 2 delivered the first useful local tools slice. The security assessment in [`docs/tools-security-assessment.md`](../tools-security-assessment.md) concluded that this implementation is a good narrow baseline, but that several important gaps remain in:

- validation consistency
- filesystem/path hardening
- tool-output handling
- Bash isolation and resource controls

This note records the subset of that assessment which should be treated as **do now** work rather than deferred architectural or compatibility hardening.

The intent is to keep the scope small, reviewable, and risk-oriented:

- fix foundational safety gaps now
- avoid large redesigns that fit better with later roadmap phases
- prevent Phase 3 persistence/resume and Phase 4 robustness work from building on avoidable tool-safety weaknesses

## Position relative to the roadmap

Phase 2.1 is not a new product stage with a broader feature goal. It is a short hardening checkpoint between the initial Phase 2 implementation and later roadmap work.

It exists because the roadmap already treats the following as real completeness gates for early phases:

- safety and correctness first
- permission safety
- file mutation safety
- unsafe cases fail clearly rather than silently degrading

Accordingly, Phase 2.1 should focus on closing the most important security and correctness gaps that still sit inside the practical Phase 2 safety boundary.

## In scope now

The following work should be completed in Phase 2.1.

### 1. Validation and error-typing consistency

Implement:

- replacement of remaining plain `ValueError` argument failures in tools with `ToolArgumentError`
- an explicit validation step before permission evaluation and execution
- tests proving validation failures surface as typed, predictable tool/runtime failures

Why this is in scope now:

- it is low-risk and tightly scoped
- it improves predictable deny/fail behavior
- it reduces tool-specific inconsistency in safety-sensitive paths

### 2. Path and file-safety hardening

Implement:

- dual lexical-path and resolved-path checks
- centralized protected-path policy rather than narrow embedded checks
- generalized blocking of existing non-regular files for reads and writes, including device nodes, FIFOs, and sockets where testable
- explicit symlink escape coverage for read and write paths
- targeted tests for traversal, network-style path forms, protected paths, and symlink escapes

Why this is in scope now:

- path containment and mutation safety are already part of the Phase 2 contract
- these are foundational protections, not optional polish
- later persistence and recovery work should not depend on under-specified path-safety behavior

### 3. Output budgeting for local tools

Implement:

- maximum file-size or output-size policy for `Read`
- maximum result and traversal budgets for `Glob` and `Grep`
- stdout/stderr caps for `Bash`
- clear truncation and budgeting indicators in tool results

Why this is in scope now:

- it prevents prompt flooding and resource-exhaustion cases
- it is useful for both security and reliability
- it can be added without a large architectural change

### 4. Minimal tool-output framing as untrusted data

Implement:

- explicit model-visible rendering for tool results rather than relying on arbitrary raw `output["content"]`
- prompt assembly framing that clearly marks tool output as tool-produced, untrusted content
- tests proving prompt-facing tool output is labeled and bounded

Why this is in scope now:

- it is the most immediate prompt-injection reduction available in the current architecture
- it lowers the risk of carrying unsafe assumptions into Phase 3 persistence and resume work
- it does not require the full transcript-structure redesign that belongs later

### 5. Minimal Bash isolation and cleanup hardening

Implement:

- subprocess environment scrubbing or minimization by default
- full process-group cleanup on timeout
- output-size caps if not already covered by the output-budgeting work above
- regression tests for timeout cleanup and reduced environment inheritance

Why this is in scope now:

- the security assessment identifies Bash as the highest-priority hardening area
- inherited environment exposure and incomplete timeout cleanup are concrete current risks
- these changes materially improve safety without requiring a full Bash execution redesign yet

## Explicitly out of scope for Phase 2.1

Phase 2.1 should remain a short hardening checkpoint. The following work is valuable but should not be treated as required here.

### Deferred to Phase 3 or later persistence-alignment work

- full separation of transcript items, tool-result records, and prompt-normalization inputs
- replay-safe transcript/result normalization structures
- result-closure semantics designed for future resume and persistence guarantees

### Deferred primarily to Phase 4

- richer `PermissionDecision` metadata such as policy source and normalized resource records
- a broader layered whole-tool policy engine before tool-specific checks
- more advanced approval-mode completeness and policy-shaping behavior
- Bash execution split into argv-safe execution vs approval-required shell-evaluated execution
- deeper command-policy hardening around network-capable and side-effect-heavy programs
- PowerShell support and PowerShell-specific safety parity if still needed

### Deferred to Phase 5

- poisoning/replay defenses tightly coupled to compaction, reconstruction, and recovery boundaries

### Deferred to Phase 10 or targeted compatibility hardening

- enterprise-style managed-policy completeness
- migration-completeness and broader compatibility polishing if still justified by real use

## Expected deliverables

Phase 2.1 should produce the following concrete outputs:

- consistent typed validation failures across the current local tools
- a shared path-policy path used by file tools and search tools where applicable
- explicit denial of protected and non-regular-file access in typed, user-visible form
- bounded tool outputs for file, search, and shell tools
- model-visible tool-result rendering that labels content as untrusted tool output
- safer Bash subprocess behavior with reduced environment exposure and better timeout cleanup
- tests for the main threat-focused cases listed below

## Completeness criteria

Phase 2.1 is complete when all of the following are true:

- remaining argument-validation failures in the current local tools surface as `ToolArgumentError` rather than plain `ValueError`
- permission evaluation and execution operate on validated tool input rather than ad hoc raw parsing paths
- path handling rejects lexical traversal attempts and resolved out-of-workspace escapes
- existing non-regular files are rejected clearly for read/write operations
- representative tests cover symlink escapes, protected paths, and special-file denials where testable
- `Read`, `Glob`, `Grep`, and `Bash` produce bounded model-visible output with truncation or budget signaling
- prompt-facing tool output is labeled as tool-produced, untrusted content
- timed-out Bash executions clean up descendant processes as intended by the implementation
- Bash does not inherit the full ambient environment by default

## Ordered execution plan

The work should land in the following order.

### 1. Validation and typed-failure cleanup

Land first:

- replace remaining plain `ValueError` uses with `ToolArgumentError`
- introduce the explicit validation step in the tool/session path
- add narrow tests for validation failures at both tool and session levels

Why first:

- low blast radius
- improves consistency for all later hardening work
- makes subsequent path and permission failures easier to reason about in tests

### 2. Shared path-policy hardening

Land second:

- add a shared path-policy layer or equivalent shared API
- implement lexical checks, resolved containment checks, protected-path rules, and non-regular-file checks
- route file and search tools through the shared path-safety path
- add targeted path-focused tests

Why second:

- this is the most important foundational safety closure after typed validation
- it stabilizes the rules that file, search, and mutation tools should all share

### 3. Output budgeting across tools

Land third:

- add file-size and result-count caps for `Read`, `Glob`, and `Grep`
- add stdout/stderr caps for `Bash`
- expose truncation/budget metadata in results and tests

Why third:

- it limits resource exhaustion and prompt flooding before prompt-facing rendering changes are finalized
- it keeps tool-result framing work simpler because outputs are already bounded

### 4. Prompt-facing tool-result framing

Land fourth:

- replace implicit raw prompt-facing rendering with explicit tool-result rendering
- mark tool outputs as untrusted data in prompt assembly
- verify bounded, labeled rendering with tests

Why fourth:

- by this point, validation, path safety, and output budgets are already stabilized
- explicit rendering can then build on known-safe, bounded result shapes

### 5. Bash isolation and timeout-cleanup hardening

Land fifth:

- minimize inherited environment
- add process-group cleanup on timeout
- finish Bash-specific regression coverage

Why fifth:

- Bash is the highest-risk tool, but these changes are easier to land once shared failure handling and output budgeting are already in place
- keeping Bash hardening as a focused final step helps preserve reviewability

### 6. Close-out verification pass

Finish with:

- integration tests covering representative file and Bash workflows through the runtime event path
- review of any intentionally deferred items against the roadmap landing zones
- documentation updates if behavior or limits need to be made user-visible

## Suggested testing additions

Phase 2.1 should add or expand tests for at least:

- validation failures surfacing as `ToolArgumentError`
- symlink inside workspace resolving outside workspace
- write or read attempts against non-regular files in workspace where testable
- traversal and network-path variants rejected clearly
- protected-path denials remaining enforced
- oversized `Read` results truncated or blocked per policy
- `Glob` and `Grep` enforcing traversal or result budgets
- prompt-facing tool output labeled as untrusted
- `Bash` timeout cleanup removing subprocess trees as intended
- `Bash` default environment exposure being reduced relative to the parent process

## Deferred item landing zones

For clarity, the main items intentionally deferred by this note should land approximately here:

- richer permission metadata and approval/policy hardening -> **Phase 4**
- argv-first vs shell-evaluated Bash redesign -> **Phase 4**
- transcript/result/prompt-state structural separation for persistence safety -> **Phase 3**, with deeper recovery alignment in **Phase 5**
- advanced replay/poisoning hardening across compaction/recovery -> **Phase 5**
- managed-policy and migration-completeness compatibility work -> **Phase 10** if still justified

## Bottom line

Phase 2.1 should be a short, explicit hardening step that closes the most important current safety gaps in the local tools layer.

The key discipline is to fix the foundational issues now:

- consistent typed validation
- stronger path and special-file safety
- bounded tool outputs
- explicit untrusted tool-output framing
- minimal Bash isolation and cleanup hardening

while deferring larger policy and architecture redesigns to the roadmap phases where they fit more naturally.