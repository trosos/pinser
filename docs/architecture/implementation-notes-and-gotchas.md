# Implementation notes, safety invariants, and gotchas for a clean-room rewrite

This document records implementation-level details that are easy to miss during a rewrite because they are not merely type/interface contracts.

It focuses on:
- sandboxing and permission-system behavior
- file/tool safety invariants
- recovery mechanisms and runtime workarounds
- platform/security edge cases
- operational behaviors that appear bug-fix-driven and should likely survive a rewrite

This document complements:
- `docs/hld.md`
- `docs/interfaces-and-endpoints.md`
- `docs/tool-contracts.md`
- `docs/remote-api.md`

Primary inspected sources for this pass:
- `src/Tool.ts`
- `src/query.ts`
- `src/QueryEngine.ts`
- `src/tools/FileReadTool/FileReadTool.ts`
- `src/tools/FileEditTool/FileEditTool.ts`
- `src/tools/FileWriteTool/FileWriteTool.ts`
- `src/tools/NotebookEditTool/NotebookEditTool.ts`
- `src/tools/GlobTool/GlobTool.ts`
- `src/tools/GrepTool/GrepTool.ts`
- `src/tools/BashTool/shouldUseSandbox.ts`
- `src/utils/sandbox/sandbox-adapter.ts`
- `src/utils/permissions/filesystem.ts`

Where this document says a behavior should be preserved, that means it appears to be a correctness or safety property, not just an incidental implementation detail.

---

## 1. Tool sandboxing

The existing docs mention permissions and safety metadata, but sandboxing deserves its own explicit treatment because it is more than a boolean “on/off” feature.

## 2.1 Sandboxing is primarily a shell/runtime containment mechanism
From inspected code, sandboxing primarily affects shell-like command execution rather than all tools equally.

Observed evidence:
- `src/tools/BashTool/shouldUseSandbox.ts`
- `src/utils/sandbox/sandbox-adapter.ts`
- multiple sandbox-specific UI and permission integration files

### Rewrite implication
A rewrite should not model sandboxing as merely “permission granted or denied.”
It is a distinct execution mode with:
- filesystem restrictions
- network restrictions
- configuration-derived allow/deny sets
- runtime availability checks
- explicit override behavior
- surfaced sandbox violation reporting

---

## 2.2 Sandbox enablement is conditional, and failure-to-initialize matters
The runtime distinguishes between:
- sandbox enabled and available
- sandbox configured but unavailable
- policy requiring sandbox with fail-fast startup if unavailable
- sandbox disabled with warning fallback to unsandboxed execution

### Preservation requirement
A rewrite should preserve:
- sandbox availability detection at startup
- a mode where missing sandbox support aborts startup
- a mode where missing sandbox support downgrades with explicit warning

This is operationally important, not just UX.

---

## 2.3 Sandbox use for Bash is per-command, not merely session-global
From `shouldUseSandbox.ts`, sandboxing for Bash is decided per invocation using at least:
- global sandbox enabled state
- `dangerouslyDisableSandbox`
- policy allowing unsandboxed commands or not
- command-specific excluded-command matching

### Preservation requirement
A rewrite must preserve per-command sandbox routing.
It should not assume “session sandbox mode” alone is sufficient.

---

## 2.4 `dangerouslyDisableSandbox` is real behavior and must remain policy-controlled
Observed behavior:
- Bash input supports `dangerouslyDisableSandbox?: boolean`
- unsandboxed execution is allowed only if policy permits it
- prompt text strongly instructs the model to default to sandbox and only bypass when there is evidence of sandbox-caused failure or an explicit user request

### Preservation requirement
A rewrite should preserve:
- the existence of an explicit unsandboxed override path
- policy-level ability to disable that path entirely
- model guidance that sandbox bypass is exceptional and per-command

---

## 2.5 Excluded commands are convenience behavior, not the core security boundary
`shouldUseSandbox.ts` explicitly states excluded commands are a convenience feature and not the true security boundary.

### Preservation requirement
A rewrite should preserve the architectural distinction between:
- convenience command-routing heuristics
- actual permission/sandbox enforcement

This matters so the rewrite does not accidentally rely on excluded-command matching as the primary safety mechanism.

---

## 2.6 Sandbox configuration is synthesized from several config surfaces
From `sandbox-adapter.ts`, sandbox runtime configuration is derived from:
- general settings
- permission allow/deny rules for tools like Read/Edit/WebFetch
- sandbox-specific filesystem and network settings
- policy settings that can restrict allowed domains/read paths to managed-only sets
- runtime-discovered worktree and cwd state
- additional directories and temp directories

### Preservation requirement
A rewrite should preserve this synthesis model.
Do not treat sandbox config as a static hand-written config blob; it is computed from the higher-level permission/settings model.

---

## 2.7 The sandbox has built-in hardening beyond user settings
Observed built-in protections include:
- always denying writes to Pinser settings files
- always denying writes to managed settings drop-in directories
- always denying writes to `.pinser/skills`
- protecting against bare-git-repo file planting at cwd
- allowing temp/cwd/additional directories needed for legitimate tool operation
- allowing worktree main-repo paths when needed for Git operations in a worktree

### Preservation requirement
A rewrite should preserve these built-in hardening rules even if the sandbox backend changes.
They are not merely user preferences.

---

## 2.8 Sandboxing and network policy are partially driven by WebFetch permissions
Observed behavior in `sandbox-adapter.ts`:
- allowed and denied network domains are derived in part from WebFetch allow/deny permission rules (`domain:host` style)
- policy may force use of only managed sandbox domains

### Preservation requirement
A rewrite should preserve the coupling between tool permission state and sandbox network policy.
Without that, WebFetch permissions and sandbox egress policy can drift apart.

---

## 3. File-tool safety invariants that should definitely be preserved

These are central to safe implementation.

## 3.1 Read-before-write is a core safety invariant
Observed in:
- `FileEditTool`
- `FileWriteTool`
- `NotebookEditTool`

### Verified behavior
Write/edit operations generally require:
- the file to have been read earlier in the session
- that read to have been a full read, not a partial read/view
- the file to remain unchanged since the read

### Preservation requirement
A rewrite should preserve read-before-write as a fundamental editing invariant.
This is one of the most important implementation details to not lose.

---

## 3.2 Staleness checks are not just timestamp checks
Observed behavior in `FileEditTool`:
- if mtime indicates the file changed since the last read, the tool may compare content as a fallback on Windows because timestamps can change without content changes

### Preservation requirement
A rewrite should preserve:
- stale-read protection
- content-based fallback when timestamps are unreliable on some platforms

Do not reduce this to a naive timestamp-only check.

---

## 3.3 Partial reads are intentionally insufficient for later write safety
Observed behavior:
- if the file was read only partially, later edit/write is rejected until a full read occurs

### Preservation requirement
A rewrite should preserve the distinction between:
- read for inspection/search/navigation
- read sufficient to authorize full-file mutation

---

## 3.4 Notebook editing is intentionally separated from text editing
Observed behavior:
- `.ipynb` edits are rejected by `FileEditTool`
- notebook changes must go through `NotebookEditTool`
- notebook edits still obey read-before-write and stale-read invariants

### Preservation requirement
A rewrite should preserve notebook-specific mutation semantics rather than treating notebooks as generic text files.

---

## 3.5 File reads avoid dangerous special files
Observed behavior in `FileReadTool`:
- explicit blocklist for special device paths such as `/dev/zero`, `/dev/random`, `/dev/tty`, stdio aliases, and `/proc/*/fd/[0-2]`

### Preservation requirement
A rewrite should preserve these protections or an equivalent generalized “unsafe special file” policy.
This prevents hangs, infinite output, and nonsensical reads.

---

## 3.6 File reads include de-duplication behavior for unchanged files
Observed behavior in `FileReadTool`:
- repeated reads of the exact same range can produce an unchanged-file stub instead of resending content
- this is explicitly motivated by context/caching efficiency

### Preservation requirement
A rewrite does not have to preserve the same implementation, but it should likely preserve the semantic optimization:
- repeated unchanged reads should not unnecessarily duplicate full file contents into context/transcript

This is a meaningful runtime optimization, not just a micro-optimization.

---

## 3.7 File writes preserve caller-provided line endings
Observed behavior in `FileWriteTool` and related code:
- written content preserves the line endings contained in the caller’s content rather than normalizing to previous file style

### Preservation requirement
A rewrite should preserve exact-content semantics for full-file write operations.
Do not silently normalize line endings unless intentionally redesigning the contract.

---

## 4. Windows / UNC / path-security behaviors that are very important

These appear repeatedly across tools, which is a strong sign they were added in response to real bugs or security issues.

## 4.1 UNC paths must not trigger filesystem probing before permission checks
Observed in many tools:
- `FileReadTool`
- `FileWriteTool`
- `FileEditTool`
- `NotebookEditTool`
- `GlobTool`
- `GrepTool`
- `LSPTool`
- permission utilities

### Verified rationale
Comments explicitly say UNC path probing on Windows can trigger SMB/WebDAV/network access and leak NTLM/Kerberos credentials.

### Preservation requirement
A rewrite should preserve this pattern:
- detect suspicious UNC/network paths early using string/path analysis
- avoid filesystem access on them before policy/permission handling
- treat this as a defense-in-depth security invariant

This is a very important implementation detail.

---

## 4.2 Dangerous path detection is broader than simple deny lists
Observed in `permissions/filesystem.ts`:
- dangerous files and directories include `.git`, `.vscode`, `.idea`, `.pinser`, and several shell/git/config files
- there is case-normalized comparison to avoid bypass on case-insensitive filesystems
- there is handling for traversal, alternate data streams, DOS device names, and path normalization issues

### Preservation requirement
A rewrite should preserve a real path-security layer, not only tool-local checks.
This should include:
- canonicalization
- case-normalized comparison where relevant
- dangerous-directory/file classification
- platform-specific invalid/suspicious path handling

---

## 4.3 Narrow skill-scoped exceptions exist inside generally dangerous areas
Observed in `getPinserSkillScope()`:
- `.pinser` is broadly dangerous
- but the system can generate a narrower permission suggestion for a single skill directory under `.pinser/skills/{name}`
- it carefully rejects traversal and wildcard-like names to avoid expanding the scope accidentally

### Preservation requirement
A rewrite should preserve this principle:
- broad dangerous zones may still need carefully-scoped sub-exceptions
- those exceptions must be syntactically sanitized to avoid permission over-broadening

---

## 4.4 macOS screenshot path quirks are handled explicitly
Observed in `FileReadTool`:
- alternate resolution is attempted because some macOS versions use thin space vs normal space in screenshot filenames before AM/PM

### Preservation requirement
This exact workaround is optional, but it is worth preserving because it solves a concrete user-facing path-resolution bug.

---

## 5. Query-loop recovery and runtime glitch-handling that should survive a rewrite

There are several subtle runtime workarounds here that are important.

## 5.1 Tombstones are used to repair orphaned partial assistant output
Observed in `query.ts`:
- when streaming fallback occurs, previously yielded partial assistant messages are tombstoned so UI/transcript remove them
- motivation includes invalid thinking signatures and partial/orphaned output consistency

### Preservation requirement
A rewrite should preserve an explicit transcript-repair mechanism like tombstones.
Without it, fallback and retry behavior will leave inconsistent transcript artifacts.

---

## 5.2 Tool results are synthesized on interruption/failure to keep tool-use pairs consistent
Observed in `query.ts`:
- `yieldMissingToolResultBlocks(...)` emits synthetic error tool_results for tool_use blocks when execution aborts or fails before normal completion

### Preservation requirement
A rewrite should preserve the invariant:
- every emitted tool_use that becomes externally visible should eventually receive a matching tool_result or explicit synthetic failure result

This is vital for transcript consistency and downstream consumers.

---

## 5.3 Fallback retries scrub or discard state that cannot safely survive model switch
Observed behavior on fallback:
- clear assistant messages/tool results/tool uses from failed attempt
- discard pending streaming-tool executor results
- strip signature blocks in some cases
- emit warning system message
- retry in the same logical turn

### Preservation requirement
A rewrite should preserve the fact that model fallback is not just “try again with a different model.”
It also requires cleanup of invalid partial state before retry.

---

## 5.4 Prompt-too-long recovery is multi-stage, not one-shot
Observed in `query.ts`:
- collapse-drain retry first
- then reactive compact retry
- then surface error if recovery fails
- stop hooks are intentionally skipped on these API-error paths to avoid loops

### Preservation requirement
A rewrite should preserve this staged recovery idea.
Even if the exact mechanisms change, the system should still:
- attempt cheap/local recovery first
- then attempt heavier compaction/recovery
- avoid hook-induced infinite retry loops on unrecoverable API errors

---

## 5.5 Max-output-token recovery is a specialized continuation protocol
Observed in `query.ts`:
- withheld `max_output_tokens` errors
- optional escalation retry with a larger output cap
- then meta-message continuation asking model to resume directly without apology or recap
- bounded retry count

### Preservation requirement
A rewrite should preserve dedicated max-output recovery rather than lumping it into generic failure handling.
This is a materially different failure mode.

---

## 5.6 Stop hooks are intentionally skipped for API-error cases to avoid retry spirals
Observed in `query.ts` comments:
- running stop hooks on API-error outputs creates a death spiral: error → hook blocking → retry → error

### Preservation requirement
A rewrite should preserve this rule or a closely equivalent one.
This appears to be a learned production workaround.

---

## 5.7 Token-budget continuation is a separate continuation path
Observed in `query.ts`:
- token budget can trigger a nudge/continuation path distinct from max-output recovery
- continuation count is tracked

### Preservation requirement
A rewrite should preserve token-budget continuation as distinct from transport errors and output-cap errors.

---

## 5.8 Tool result budgeting exists to control transcript/context blow-up
Observed in `query.ts` via `applyToolResultBudget(...)` and content replacement state.

### Preservation requirement
A rewrite should preserve a mechanism that bounds large accumulated tool outputs in long-running sessions.
Even if the storage/projection mechanism changes, the budgeted replacement behavior should remain.

---

## 6. Persistence/resume gotchas that should be explicitly preserved

## 6.1 User input is persisted early for resumability
Observed in `QueryEngine.submitMessage()` comments and flow:
- user input is recorded before the turn fully completes so quick exits do not lose resumability

### Preservation requirement
A rewrite should preserve early-enough persistence of user submissions.

---

## 6.2 Not every emitted event is persisted the same way or at the same time
Observed behavior in `QueryEngine.ts`:
- some transcript writes are deferred
- some are awaited before flush-sensitive milestones
- partial-message persistence is configurable

### Preservation requirement
A rewrite should preserve the distinction between:
- UX-visible streaming
- durable transcript persistence
- flush boundaries needed for resume correctness

---

## 6.3 Orphaned permission handling is part of session recovery
Observed in `QueryEngine.ts`:
- orphaned permission state can be detected and handled once per session flow
- permission denials are accumulated and reported

### Preservation requirement
A rewrite should preserve explicit handling of interrupted/orphaned permission flows, especially for resumable/headless contexts.

---

## 7. Permission-engine details easy to miss in implementation

## 7.1 Permission prompts can be suppressed in background/automated contexts
Observed in `ToolPermissionContext`:
- `shouldAvoidPermissionPrompts`
- `awaitAutomatedChecksBeforeDialog`
- `prePlanMode`

### Preservation requirement
A rewrite should preserve permission behavior that varies by execution context, not just by tool/path.

---

## 7.2 Allow/deny/ask semantics are not only about execution; they also shape suggestions and visibility
Observed across tools and permissions utilities:
- permission rules influence tool availability, sandbox config, user suggestions, and prompt behavior

### Preservation requirement
A rewrite should preserve permission state as a first-class cross-cutting system, not a thin wrapper around “yes/no before call.”

---

## 8. Specific glitches/workarounds I would expect to remain valid in a rewrite

These are exactly the sorts of things I would want implementation teams to know up front.

1. **Windows/UNC credential-leak avoidance**
   - still valid
   - should remain explicit in the rewrite

2. **Read-before-write and stale-read protection**
   - still valid
   - should remain a mandatory editing invariant

3. **Fallback-induced transcript repair via tombstones**
   - still valid
   - any streaming rewrite will need an equivalent

4. **Synthetic tool_result generation on interruption**
   - still valid
   - avoids malformed tool-use sequences

5. **Skipping stop hooks on API-error recovery paths**
   - still valid
   - likely prevents expensive infinite loops in production

6. **Windows mtime false positives handled via content comparison fallback**
   - still valid
   - worthwhile to preserve

7. **macOS screenshot thin-space filename workaround**
   - likely still valid for compatibility
   - small cost, real user benefit

8. **Bare-git-repo planting mitigation around sandboxed execution**
   - definitely worth preserving if the rewrite still has mixed sandboxed/unsandboxed git interactions

9. **Protection of `.pinser/settings*` and `.pinser/skills` from unsafe modification**
   - still valid
   - should remain built-in hardening, not merely policy-configurable

10. **Budgeting/dedup of repeated file/tool output to avoid transcript explosion**
   - still valid
   - especially important for long-running sessions

---

## 9. Additional implementation-critical topics

The following topic areas are part of the compatibility surface and must be preserved by a rewrite because they determine safety, recovery correctness, and runtime behavior:

### 9.1 Shell-tool safety model
The shell subsystem depends on all of the following, which are documented in `docs/bash-and-powershell-safety.md`:
- sandbox decision matrices
- read-only classification matrices
- destructive-command and dangerous-pattern heuristics
- UNC/WebDAV/credential-leak mitigations
- sandbox override behavior and policy gating
- backgrounding semantics and task identity

### 9.2 Persistence and replay semantics
Transcript durability behavior depends on all of the following, which are documented across `docs/transcript-and-persistence-semantics.md`, `docs/session-compaction-and-recovery.md`, and `docs/conversation-recovery-state-machine.md`:
- immediate vs deferred transcript writes
- replay ordering and partial-message persistence semantics
- snip/compact boundary projection behavior
- interruption classification and transcript-tail cleanup

### 9.3 Hook interaction semantics
Hook behavior is part of the runtime contract because it affects retries, failure handling, and transcript shape. The implementation must preserve:
- pre/post/stop hook timing boundaries
- blocking vs advisory hook effects
- hook interaction with retries and turn restarts
- bypass of certain hook paths during API-error recovery to prevent retry spirals

---

## 10. Rewrite checklist for implementation-critical details

A compatible rewrite must explicitly preserve all of the following:

- async streaming turn API
- transcript repair events (tombstones or equivalent)
- synthetic tool_result completion for aborted tool uses
- staged prompt-too-long recovery
- dedicated max-output-token recovery
- same-turn model fallback with partial-state cleanup
- tool-result budget/replacement mechanism
- read-before-write invariant
- stale-read/content-fallback logic
- notebook-specific mutation path
- blocked special-file reads
- UNC/network-path prevalidation without filesystem probing
- dangerous path normalization and case-insensitive comparison rules
- built-in protection for settings/skills/config-sensitive paths
- sandbox config synthesis from settings + permission rules
- policy-controlled unsandboxed override behavior
- background-context permission suppression behavior
- early-enough persistence for resumability
- distinction between durable transcript state and ephemeral stream/UI state
- durable team task-list coordination semantics

If those are all covered, the rewrite is much less likely to miss a critical implementation behavior.

---

## 11. Confidence and limits

High confidence:
- the safety/workaround items above were directly supported by inspected source and comments
- many of these behaviors are clearly the result of prior production bugs or security hardening

Lower confidence:
- exact Bash/PowerShell safety matrices, since I did not fully inspect those implementations in this pass
- some persistence details outside the directly inspected turn engine files

That said, the items documented here are exactly the ones I would want in front of an implementation team before a clean-room rewrite starts.
