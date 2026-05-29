# Tools security assessment and implementation plan

This document assesses the current Phase 2 tools implementation against the documented threat model in [`threat-model.md`](./threat-model.md), then proposes concrete improvements and an implementation plan.

## Scope reviewed

Reviewed implementation surface:

- tool protocol and registry
- session tool loop and tool-result handling
- path safety and file-state tracking
- local tools: `Read`, `Write`, `Edit`, `Glob`, `Grep`, `Bash`
- current tool-focused tests

Primary source references:

- [`threat-model.md`](./threat-model.md)
- [`phase2/tool-runtime-implementation-note.md`](./phase2/tool-runtime-implementation-note.md)
- architecture docs referenced from that note

## Executive summary

The current implementation is a good narrow Phase 2 baseline, and it already addresses several important threats:

- model output does not directly execute arbitrary actions; it must go through registered tools
- file mutation is constrained by a workspace-root path-safety layer
- `Write` and `Edit` enforce read-before-write and stale-read checks when a `FileStateTracker` is present
- the session emits explicit permission, denial, blocked, and failure events
- `Bash` uses a conservative allowlist-oriented classifier and requires approval for many risky command forms

However, the implementation only partially satisfies the documented threat model. The biggest current gaps are:

1. tool safety is inconsistent across tools and relies too much on each tool doing its own validation
2. several tools raise plain `ValueError` instead of typed runtime errors, which weakens predictable denial/failure handling
3. path safety is narrower than the threat model requires, especially for symlink escapes, special files, and protected reads
4. shell execution still launches `/bin/bash -lc <command>` with the inherited environment and without output budgeting or stronger policy shaping
5. tool results are inserted into prompt context as raw text without provenance or injection-resistant framing
6. permission decisions are too minimal to support the threat model’s layered, auditable policy model

Overall assessment: **reasonable early baseline, but not yet sufficient to claim close conformance with the documented threat model**.

## Threat-model alignment assessment

## 1. Unsafe model-to-action execution

### What is good now

- The session only executes tools that are explicitly registered.
- Each tool has a permission hook via `decide_permission()`.
- The session distinguishes deny, ask, blocked, and failed outcomes.
- `dontAsk` behavior is effectively enforced by converting `ASK` to denial in the session loop.
- `Bash` denies some obviously dangerous prefixes such as `sudo`/`su`/`doas` and requires approval for compound commands, redirections, and substitutions.

### Gaps

- The tool contract does not include typed input validation as a first-class step before permission evaluation; tools parse raw `Mapping[str, Any]` themselves.
- Some tools raise plain `ValueError` during argument checking. Those exceptions are caught generically and surfaced as failures, but this is inconsistent with the repository’s typed runtime error direction.
- There is no runtime-level whole-tool policy layer before tool-specific checks, despite the architecture note calling for layered evaluation.
- There is no tool-call ID or richer audit metadata, so later reviewability and closure semantics are weaker than planned.
- The session currently appends `ToolResultMessage` directly into transcript state. That is acceptable for early local prompting, but it increases the chance that tool output is treated too much like trusted conversational context.

### Assessment

**Partially mitigated.** The current design blocks direct model-to-action bypass, but the policy and validation model is still too thin for the documented requirements.

## 2. Filesystem escape and path-based attacks

### What is good now

- `PathSafety` resolves relative paths against the workspace root.
- Resolved paths must remain within the workspace for normal file reads/writes.
- network-like paths (`//` and `\\`) are recognized early and converted to approval-required outcomes.
- writes to top-level `.pinser` and `.git` are denied.
- known dangerous read paths such as `/dev/zero` and related devices are blocked.
- `Glob` and `Grep` resolve candidates and skip files whose resolved path falls outside the workspace.

### Gaps

- protected-path enforcement is much narrower than the threat model and architecture describe. It currently only blocks writes to top-level `.pinser` and `.git`, and does not cover other sensitive files or shell profiles.
- read protection is minimal. The threat model emphasizes protecting secrets and config-sensitive areas, but current reads are broadly allowed inside the workspace.
- special-file handling is incomplete. Reads block a few hard-coded `/dev/*` paths, but writes do not explicitly block special files, FIFOs, sockets, or device nodes if they appear inside the workspace.
- `resolve(strict=False)` gives a canonical path shape, but the implementation does not explicitly perform a lexical-path check plus a resolved-path check as called for by the threat model.
- there is no explicit symlink policy for write targets. A symlink inside the workspace that points outside the workspace will likely be caught by resolved containment, which is good, but this is not made explicit or tested enough.
- `Glob` and `Grep` do not bound traversal size, result count, or file size, which makes them susceptible to resource-exhaustion scenarios.

### Assessment

**Partially mitigated, with notable hardening gaps.** The core workspace containment check exists, but the threat-model coverage is not complete yet.

## 3. Transcript poisoning and unsafe resume

### What is good now

- progress is kept separate from transcript content.
- tool events are distinct from assistant/user messages.
- tool results are stored explicitly as `ToolResultMessage`, which is better than flattening them into assistant text.

### Gaps

- there is no provenance or structured framing in prompt assembly for tool results; the model sees only raw tool-result text.
- there is no escaping, delimiting, or metadata to distinguish untrusted file contents from authoritative runtime instructions once a tool result reaches prompt assembly.
- while full persistence/resume is not implemented yet, the current transcript shape would make future poisoning easier if tool outputs are later replayed without normalization.
- tool results can include large raw file contents or command outputs without budgeting.

### Assessment

**Only lightly mitigated.** This is acceptable for a local Phase 2 prototype, but it is materially below the threat model’s stated bar for untrusted transcript and external content handling.

## 4. Untrusted external content influencing the model

### What is good now

- only local tools are implemented; remote fetch/search/MCP are not in this slice.
- `Bash`, `Read`, `Grep`, and `Glob` outputs still pass through the tool system instead of becoming direct actions.

### Gaps

- untrusted content from files and shell output is passed straight back into prompt context with no framing like “tool output; treat as untrusted data”.
- there is no output redaction path for likely secrets discovered by tools.
- there is no result truncation or summarization policy, which means prompt injection payloads can be passed through at full size.

### Assessment

**Weakly mitigated.** The runtime prevents direct authority transfer, but it does not yet reduce prompt-injection exposure from tool results.

## 5. Multi-agent and background-task abuse

### What is good now

- background Bash execution is explicitly rejected in Phase 2.

### Gaps

- none of the broader worker/delegation threat controls are implemented in this local tools slice.
- the current assessment can only say those features are deferred, not secured.

### Assessment

**Out of scope in implementation, but still open relative to the overall threat model.**

## 6. Remote integration and credential risk

### What is good now

- remote integrations are not present in the current tool slice.

### Gaps

- `Bash` inherits the ambient process environment, which may expose secrets to subprocesses and command output.
- shell output is returned verbatim and may contain secrets from the environment, config files, or developer tooling.

### Assessment

**Mostly deferred, but `Bash` already creates a local credential-exposure risk.**

## Detailed findings by component

## Tool protocol and permission model

Current strengths:

- stable tool naming
- explicit permission request and decision hooks
- structured execution result object

Current weaknesses:

- no typed validated input object
- no explicit read-only/destructive metadata on the tool contract
- no tool-call identifier in invocation/result pairing
- `PermissionDecision` carries only `kind` and optional free-form `reason`
- no machine-readable reason code, policy source, or normalized resource metadata

Improvement priority: **high**

## Session tool loop

Current strengths:

- denial, block, failure, and completion are separate event types
- tool failures usually do not crash the whole turn
- maximum assistant/tool steps bound prevents simple infinite loops

Current weaknesses:

- no distinct validation step before permission evaluation
- `ASK` is converted to deny for `dontAsk`, but there is no explicit permission mode object in the session path
- exceptions from argument parsing can still emerge from permission-building code paths unpredictably
- tool results are appended to transcript and later replayed to the model as raw content
- `_render_tool_result_message()` privileges `output["content"]` when present, which allows tools to inject arbitrary prompt-facing text without consistent framing

Improvement priority: **high**

## Path safety

Current strengths:

- workspace containment enforced on resolved paths
- top-level protected write paths for `.git` and `.pinser`
- basic network-path detection
- basic blocked read-device list

Current weaknesses:

- no dual lexical-plus-resolved enforcement API
- no generalized special-file blocking by stat/type
- no explicit symlink policy tests for writes and reads
- protected-path coverage is narrow
- no file-size or traversal-budget limits for read/search operations

Improvement priority: **high**

## File-state tracker and mutation safety

Current strengths:

- read-before-write invariant exists
- partial-read and stale-read states are modeled
- `Edit` maps generic overwrite safety failures into edit-specific user-facing errors

Current weaknesses:

- safety depends on tools being instantiated with a `FileStateTracker`; the contract does not force this for mutation tools
- the stale-read check is not explicitly documented or tested as a tight critical section around write
- there is no file locking or retry discipline around the read-check-write sequence

Improvement priority: **medium to high**

## Bash tool

Current strengths:

- conservative classification of many risky forms
- disallows background execution for now
- can reject sandbox bypass via policy
- runs with explicit `cwd`
- enforces execution timeout

Current weaknesses:

- uses `/bin/bash -lc`, which re-enables shell parsing after analysis; analysis is heuristic and incomplete
- inherits ambient environment by default
- no stdout/stderr size limits
- no process-group kill / child cleanup on timeout
- read-only classification is heuristic and can be bypassed by shell features not covered by current parsing
- command policy is prefix-based and string-based rather than AST- or exec-argument-based
- no sandbox integration despite the architecture’s shell-safety intent

Improvement priority: **highest**

## Search tools: `Glob` and `Grep`

Current strengths:

- results are kept workspace-relative
- resolved out-of-workspace paths are skipped

Current weaknesses:

- no result-count cap
- no byte/file-count traversal budget
- `re.compile()` accepts arbitrary patterns that may be expensive on large inputs
- exceptions are plain `ValueError`, not typed tool errors
- no binary-file or oversized-file policy beyond decode failure behavior

Improvement priority: **medium**

## File read tool

Current strengths:

- path checked before read
- read is recorded for later write safety

Current weaknesses:

- plain `ValueError` for bad input
- no file-size limit
- no explicit binary/special-file check beyond hard-coded device path denylist
- raw file content is emitted into prompt context without framing or truncation

Improvement priority: **medium to high**

## Suggested improvements

## Priority 0: tighten correctness and error typing

1. **Replace all plain `ValueError` argument failures with `ToolArgumentError`.**
   - Applies at least to `Read`, `Glob`, and `Grep`.
   - This makes failure handling predictable and aligned with repository direction.

2. **Add an explicit validation phase in the session before permission evaluation.**
   - Introduce `validate_input(raw_args) -> validated_input` in the tool contract or an equivalent typed parser.
   - Permission checks and execution should consume validated input only.

3. **Expand `PermissionDecision` to include machine-readable metadata.**
   - Suggested fields: `kind`, `reason_code`, `message`, `resource`, `policy_source`.

## Priority 1: harden path and file safety

4. **Implement dual lexical and resolved path checks.**
   - Reject traversal and suspicious path forms lexically before filesystem interaction.
   - Then enforce resolved containment and protected-path rules.

5. **Add generalized special-file blocking.**
   - For existing paths, reject device nodes, FIFOs, sockets, and other non-regular files for both read and write.

6. **Broaden protected-path policy.**
   - Keep `.pinser/` and `.git/` blocked.
   - Add documented handling for common sensitive dotfiles and shell startup files when inside workspace scope if that matches architecture intent.
   - At minimum, centralize protected-path rules rather than embedding only top-level names.

7. **Add read/search budgeting.**
   - Maximum file size for `Read`
   - Maximum files scanned and maximum matches returned for `Glob`/`Grep`
   - Clear truncation indicators in tool results

8. **Strengthen mutation critical section semantics.**
   - Re-check current file content immediately before write with no avoidable async gap.
   - Add tests for stale-read races where the file changes between read and write.

## Priority 2: reduce prompt-injection exposure from tool outputs

9. **Frame tool results as untrusted data in prompt assembly.**
   - Example shape: include tool name and a prefix such as `Tool output (untrusted data): ...`.
   - Longer-term, keep structured tool result objects and provider-native tool-result formatting.

10. **Truncate and summarize large tool outputs before they reach prompt context.**
    - Preserve exact output in runtime metadata if needed, but bound model-visible content.

11. **Add optional secret-redaction hooks for tool outputs.**
    - Start with conservative detection of obvious token patterns in `Bash` and `Read` output.

## Priority 3: harden Bash significantly

12. **Prefer subprocess execution without `bash -lc` for the subset of commands that can be expressed as argv safely.**
    - If shell syntax is actually required, keep requiring approval or deny under strict modes.

13. **Run Bash with a minimal, explicit environment.**
    - Default to a scrubbed environment and only pass through required variables.

14. **Add stdout/stderr output caps.**
    - Prevent prompt flooding and memory abuse.

15. **Kill the full process group on timeout.**
    - Avoid orphaned child processes.

16. **Move command classification closer to argv-level policy.**
    - Classify the parsed program/subcommand rather than relying primarily on substring heuristics.

17. **Add stronger deny rules for known exfiltration/network/process-control commands in default policy.**
    - Examples depend on desired product posture, but current policy is likely too permissive for tools such as `curl` if later allowed by approval.

## Priority 4: auditability and future-safe structure

18. **Add `tool_call_id` and propagate it through events and tool results.**
    - This aligns implementation with the Phase 2 runtime note and improves auditability.

19. **Add tool metadata such as `read_only` and `concurrency_safe`.**
    - Even if concurrency is not implemented yet, the metadata helps preserve architecture boundaries.

20. **Separate runtime-visible result metadata from model-visible result content.**
    - Do not rely on `output["content"]` as the prompt-facing source of truth.
    - Make model rendering an explicit tool method.

## Recommended implementation plan

## Phase 1: consistency and low-risk security fixes

Goal: make current tools behave consistently and improve safety without changing the overall runtime shape.

Tasks:

1. Replace remaining plain `ValueError` uses in tools with `ToolArgumentError`.
2. Add tests covering those error paths at both tool and session level.
3. Expand `PermissionDecision` with `reason_code` and `message`, while keeping current behavior compatible.
4. Add explicit `tool_call_id` generation in session execution and include it in emitted events.
5. Refactor `_render_tool_result_message()` into an explicit tool-controlled render path.

Acceptance checks:

- all tool argument failures surface as typed runtime-visible failures
- session tests assert stable permission/failure reason fields
- existing tool behavior remains functionally unchanged except for improved metadata

## Phase 2: path-safety hardening

Goal: raise filesystem protections to better match the threat model.

Tasks:

1. Introduce a shared path-policy module that performs:
   - lexical normalization checks
   - resolved containment checks
   - protected-path checks
   - existing-file special-type checks
2. Extend protected-path policy coverage and centralize the rule list.
3. Block non-regular existing files for read/write tools.
4. Add targeted tests for:
   - symlink-in-workspace to outside target
   - FIFO/socket/device handling where testable
   - protected writes under `.pinser/` and `.git/`
   - traversal and network-path variants

Acceptance checks:

- path tests cover both lexical and resolved bypass attempts
- all file tools use the shared path-policy path
- protected and special-file denials are explicit and typed

## Phase 3: output handling and injection resistance

Goal: reduce the risk that untrusted tool outputs steer the model improperly.

Tasks:

1. Introduce structured model-visible tool rendering per tool.
2. Prefix tool results in prompt assembly as untrusted tool output.
3. Add size limits/truncation for `Read`, `Grep`, `Glob`, and `Bash` outputs.
4. Add tests proving large outputs are truncated and clearly labeled.
5. Add a first-pass redaction utility for obvious secrets in tool outputs and logs.

Acceptance checks:

- prompt context never receives raw unbounded tool output
- tool outputs are clearly marked as tool-produced, untrusted content
- truncation is reflected in summaries and metadata

## Phase 4: Bash hardening

Goal: make shell execution materially safer while keeping the feature usable.

Tasks:

1. Split Bash execution into:
   - safe argv-executed command path for simple commands
   - approval-required shell-evaluated path for actual shell syntax
2. Run subprocesses with a minimal environment.
3. Add output-size caps and process-group cleanup on timeout.
4. Revisit read-only classification and deny/ask defaults for network-capable or side-effect-heavy programs.
5. Add regression tests for timeout cleanup, environment scrubbing, and denial of risky forms.

Acceptance checks:

- simple read-only commands do not require full shell parsing
- timed-out commands do not leave descendant processes running
- environment exposure is minimized by default

## Phase 5: architectural alignment work

Goal: bring the implementation into closer conformity with the architecture and threat model.

Tasks:

1. Introduce typed validated input models for all tools.
2. Add whole-tool policy evaluation before tool-specific checks.
3. Separate transcript items, tool-result records, and prompt-normalization inputs more cleanly.
4. Preserve explicit result closure semantics for future persistence/resume work.
5. Add audit-oriented event fields and reason codes throughout the tool lifecycle.

Acceptance checks:

- tool execution consumes validated input objects, not raw mappings
- permission flow reflects layered evaluation
- transcript/prompt state carries enough structure for safe future normalization

## Suggested testing additions

Add or expand tests for the following threat-focused cases:

- symlinked file inside workspace resolving outside workspace
- write to FIFO or other non-regular file in workspace
- `Read` of oversized file is truncated or blocked per policy
- `Grep` and `Glob` enforce result and traversal budgets
- tool results in prompt context are labeled untrusted
- `Bash` timeout kills subprocess trees
- `Bash` does not inherit sensitive environment variables by default
- stale-read race between prior read and later write/edit
- protected-path policies remain enforced case-insensitively where applicable

## Bottom line

The current tools implementation is a solid early Phase 2 skeleton and already captures several high-value controls from the threat model, especially explicit tool mediation, path containment, write safety invariants, and conservative eventing.

But it is not yet fully aligned with the documented threat model. The most important improvements are:

- unify typed validation and permission handling
- harden path and special-file safety
- stop feeding raw, unframed tool output back into the model
- significantly strengthen `Bash` execution policy and isolation

If the project completes the implementation plan above, the tools layer will move from a promising prototype to a security posture much closer to the documented design intent.
