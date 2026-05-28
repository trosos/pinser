# Phase 2 CLI output expectations

This document records lightweight CLI output expectations for the first Phase 2 tool and safety flows.

It complements:

- [`scope.md`](./scope.md)
- [`tool-runtime-implementation-note.md`](./tool-runtime-implementation-note.md)
- [`../ui-design-contract.md`](../ui-design-contract.md)
- [`../architecture/permission-engine.md`](../architecture/permission-engine.md)
- [`../architecture/path-and-filesystem-safety.md`](../architecture/path-and-filesystem-safety.md)
- [`../architecture/bash-and-powershell-safety.md`](../architecture/bash-and-powershell-safety.md)

This note is intentionally local and practical. It does not replace the architecture or the UI design contract.

## Purpose

Phase 2 introduces real tool execution and safety decisions. Before implementation spreads, contributors need a small shared expectation for how those states should appear in the CLI.

This note defines output expectations for:

- tool running
- permission required
- denied by policy
- stale read blocked
- read-before-write blocked

It also keeps those expectations aligned with the existing CLI/UI contract:

- plain text first
- technically precise wording
- clear state transitions
- explicit safety messaging
- stable terminology

## Status and scope

These expectations apply to the current CLI-first Phase 2 implementation.

They are intended for:

- runtime event rendering
- short user-facing tool/safety messages
- plain terminal output
- integration tests that assert representative output patterns

They are not intended to freeze:

- final copy polish
- richer interactive approval UX
- future TUI presentation
- remote session event rendering

## General rules

### 1. Prefer stable event-like output for runtime flow

When the runtime is actively progressing through a turn, the CLI should prefer short, stable, event-like lines rather than prose-heavy narration.

Examples of the intended style:

- `turn-started turn_id=1 user=hello`
- `Progress: generating`
- `tool-started tool=Read path=/workspace/file.py`
- `tool-completed tool=Read path=/workspace/file.py`

This remains consistent with [`../ui-design-contract.md`](../ui-design-contract.md), which prefers stable field-like formatting for dense operational output.

### 2. Safety-relevant output must say what was blocked and why

For policy or filesystem safety blocks, the CLI should explicitly communicate:

- the action type
- the affected resource when known
- the blocking reason

Do not collapse known safety outcomes into a generic `Error: tool failed.` message.

### 3. Distinguish passive progress from action-required states

`permission required` is not ordinary progress.

If the runtime is waiting for approval, the output should make clear that continuation is blocked pending user action.

### 4. Use canonical project terms consistently

Preferred terms:

- `tool`
- `permission`
- `workspace`
- `turn`
- `denied`
- `blocked`

Avoid mixing close synonyms like `rejected`, `forbidden`, and `disallowed` unless the implementation intentionally distinguishes them.

### 5. Keep ASCII-safe plain text

The Phase 2 CLI output should remain readable in plain terminals, logs, and test captures.

Avoid requiring:

- color
- Unicode box drawing
- verbose decorative headers

## Output classes and expectations

### 1. Tool running

### Purpose

Make it visible that the runtime has moved from model generation into tool execution.

### Expected shape

A short event-like line.

Preferred pattern:

```text
tool-started tool=<ToolName> ...
```

Examples:

```text
tool-started tool=Read path=/workspace/src/app.py
tool-started tool=Glob pattern=src/**/*.py
tool-started tool=Bash command='git status --short'
```

### Notes

- include the tool name
- include the most relevant target field when practical
- do not print the full validated payload if it is noisy
- for Bash, command text may need truncation later, but Phase 2 can start simple

### Relationship to runtime events

This should correspond to a runtime-visible tool-start event, not to durable conversation content.

### 2. Tool completed

### Purpose

Show that the tool finished and control is returning to the turn loop.

### Expected shape

Preferred pattern:

```text
tool-completed tool=<ToolName> ...
```

Examples:

```text
tool-completed tool=Read path=/workspace/src/app.py
tool-completed tool=Grep pattern=TODO
tool-completed tool=Bash exit_code=0
```

### Notes

- completion output should stay compact
- the CLI does not need to dump the full model-facing tool result at this point unless a command explicitly requests verbose detail
- the assistant’s later content remains the main conversational output

### 3. Permission required

### Purpose

Communicate that the runtime cannot proceed until approval is granted or denied.

### Expected shape

Use an explicit action-required style line.

Preferred pattern:

```text
Permission required: <short action summary>
```

Examples:

```text
Permission required: run Bash command in workspace.
Permission required: write file /workspace/src/app.py.
Permission required: access suspicious path //server/share/file.txt.
```

### Minimum content

Show enough context for a decision:

- action type
- relevant resource or command summary
- when useful, that this is waiting for approval rather than merely informing

### Notes

- this should not be rendered as `Progress:`
- this should not imply that the operation already happened
- if interactive approval is not yet implemented in the first slice, the message should still be emitted before the runtime fails clearly or converts ask to deny in `dontAsk`

### 4. Denied by policy

### Purpose

Make clear that the operation was blocked by permission rules or mode, not by a crash.

### Expected shape

Preferred pattern:

```text
Denied: <short reason>
```

Examples:

```text
Denied: command denied by permission policy.
Denied: tool Bash is denied by current permission rules.
Denied: approval-required action blocked by dontAsk mode.
```

### Notes

- use `Denied:` for policy-level non-execution outcomes
- if the resource is known and concise, include it
- avoid generic wording like `operation failed`

### Distinction from blocked safety conditions

A policy deny is different from file mutation safety blocks such as stale-read and read-before-write failures.

Those should use `Blocked:` rather than `Denied:` when the semantics are local safety invariants rather than policy-rule denial.

### 5. Stale read blocked

### Purpose

Explain that a file mutation was prevented because the file changed after it was read.

### Expected shape

Preferred pattern:

```text
Blocked: file changed since last read.
```

When practical, include the file path:

```text
Blocked: file changed since last read: /workspace/src/app.py.
```

### Notes

This wording should stay explicit and technical.

Avoid vaguer alternatives like:

- `Edit failed.`
- `Write rejected.`
- `File is stale.`

The important point is that the user and model can both understand that the required next step is to read again before writing.

### 6. Read-before-write blocked

### Purpose

Explain that a mutation was prevented because the file was not fully read earlier in the session.

### Expected shape

Preferred pattern:

```text
Blocked: file was not fully read before write.
```

When practical, include the file path:

```text
Blocked: file was not fully read before write: /workspace/src/app.py.
```

### Notes

This wording should preserve the distinction documented in the architecture:

- a prior full read authorizes mutation checks to continue
- a partial read does not

If the implementation can distinguish them cleanly, a more specific message is also acceptable:

```text
Blocked: partial read does not authorize mutation: /workspace/src/app.py.
```

## Additional guidance for related outputs

### 7. Workspace/path boundary rejection

Although not one of the five required examples from `scope.md`, this will appear often in Phase 2 and should be rendered consistently.

Preferred pattern:

```text
Blocked: path is outside the workspace.
```

Or, when the protected-path rule is the reason:

```text
Blocked: path is protected by filesystem safety rules.
```

### 8. Tool execution failure

If a tool genuinely runs and fails for execution/environment reasons, use `Error:` rather than `Denied:` or `Blocked:`.

Examples:

```text
Error: Bash command exited with status 1.
Error: failed to read file: permission denied.
```

This keeps three important categories distinct:

- `Denied:` -> policy decision
- `Blocked:` -> local safety invariant or safety rule prevented mutation/access
- `Error:` -> actual execution or environment failure

### 9. Assistant output remains separate

Tool and safety lines are runtime/status output.

Assistant conversational content should remain distinct and continue to use the established style, for example:

```text
assistant: Echo: hello
```

Future tool-capable assistant output should preserve that distinction rather than merging tool status and assistant prose together into one undifferentiated block.

## Suggested runtime-to-CLI mapping

A practical mapping for the first implementation is:

- lifecycle event -> event-style line
- progress event -> `Progress: ...`
- tool-start event -> `tool-started ...`
- tool-complete event -> `tool-completed ...`
- permission-required event -> `Permission required: ...`
- policy deny event -> `Denied: ...`
- file safety block event -> `Blocked: ...`
- execution failure event -> `Error: ...`
- assistant message event -> `assistant: ...`

This keeps the output classes visually distinct while staying close to the existing Phase 1 rendering style.

## Test guidance

Integration tests should avoid overfitting to every word of future copy, but they should assert the important visible distinctions.

Representative assertions should check for output containing lines like:

- `tool-started tool=Read`
- `Permission required:`
- `Denied:`
- `Blocked: file changed since last read.`
- `Blocked: file was not fully read before write.`

Tests should also continue to ensure plain output characteristics already established in the CLI tests:

- no rich box drawing
- readable plain text
- stable labels

## Examples

### Example: normal read flow

```text
turn-started turn_id=1 user=show me src/app.py
tool-started tool=Read path=/workspace/src/app.py
tool-completed tool=Read path=/workspace/src/app.py
assistant: The file defines the CLI entrypoint.
turn-completed turn_id=1
```

### Example: permission required then denied by dontAsk

```text
turn-started turn_id=1 user=run git push
Permission required: run Bash command in workspace.
Denied: approval-required action blocked by dontAsk mode.
assistant: I could not run the command because approval was required and current mode does not allow prompting.
turn-completed turn_id=1
```

### Example: stale-read block

```text
turn-started turn_id=1 user=update src/app.py
tool-started tool=Edit path=/workspace/src/app.py
Blocked: file changed since last read: /workspace/src/app.py.
assistant: I could not update the file because it changed after the last read. Read the file again before editing.
turn-completed turn_id=1
```

### Example: read-before-write block

```text
turn-started turn_id=1 user=overwrite src/app.py
tool-started tool=FileWrite path=/workspace/src/app.py
Blocked: file was not fully read before write: /workspace/src/app.py.
assistant: I could not write the file because this session does not have a prior full read for it.
turn-completed turn_id=1
```

## Bottom line

For Phase 2, CLI output should stay plain, technical, and state-oriented.

The most important distinction to preserve is:

- progress is not permission-required
- denial is not the same as blocked-by-safety
- runtime tool status is not the same as assistant conversational output

If those categories stay explicit, the Phase 2 CLI should remain consistent with both the UI contract and the architecture documentation.