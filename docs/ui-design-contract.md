# UI design contract

This document defines a lightweight UI design contract for Pinser's current CLI-first user experience.

It is intended to keep command behavior, interaction flow, and terminal output consistent while the project is still early and the runtime contracts continue to evolve.

This is not a visual design system and not a pixel-perfect style guide. It is a practical consistency contract for contributors.

## Status and scope

This contract currently applies to:

- CLI commands
- terminal prompts and interaction flow
- streamed runtime output
- informational, warning, and error messages
- help text and command feedback

This contract does not yet define:

- a rich TUI
- themes or branding systems
- color-dependent behavior
- final release-level copy polish

Because Pinser is still in an early phase, this contract should remain lightweight. It should guide implementation without freezing experimentation too early.

## Design goals

The CLI should be:

- **technical and precise**
- **consistent across commands and output modes**
- **clear about state, safety, and failure conditions**
- **useful in both human reading and log-like inspection**
- **simple enough to extend without redesign**

The UI should help users answer these questions quickly:

- what just happened
- what is happening now
- what failed, if anything
- whether user action is needed
- what to do next

## Core principles

### 1. Prefer precision over personality
Use direct, technical wording.

Prefer:

- specific nouns
- explicit state names
- concrete actions
- bounded claims

Avoid:

- chatty filler
- ambiguous reassurance
- marketing tone
- decorative wording that hides operational meaning

### 2. Keep output predictable
Equivalent situations should produce equivalently structured output.

Users should not need to relearn:

- where to find the main result
- how errors are phrased
- how warnings differ from failures
- how the next required action is communicated

### 3. Make state transitions visible
If the CLI moves through meaningful runtime states, show them in a stable way.

Examples:

- turn started
- generating
- waiting for permission
- tool running
- task started
- task completed
- turn cancelled
- turn failed

State visibility matters more than visual flourish.

### 4. Separate information by importance
Terminal output should have a readable hierarchy, but only lightly.

Use small structural conventions such as:

- a short lead line for the primary result
- optional indented details
- blank lines between major sections when needed
- stable labels for warnings, errors, and progress

Do not create heavy formatting noise.

### 5. Safety-relevant output must be explicit
Any message involving permissions, mutation, destructive actions, sandboxing, or trust boundaries must be unambiguous.

The UI must not hide:

- what action is being requested
- what resource is affected
- whether approval is required
- whether an operation changed state
- why an operation was denied or blocked

### 6. Design for plain terminals first
All important meaning must survive in:

- plain text terminals
- logs
- environments with no color
- copy-paste into bug reports

Color and styling may help later, but must not carry essential meaning by themselves.

## Tone and writing rules

### Voice
The voice should be:

- technical
- calm
- neutral
- concise

### Preferred message style
Prefer messages that are:

- short
- specific
- action-oriented when relevant
- explicit about object and status

Examples:

- `Turn started.`
- `Permission required to run command.`
- `File update blocked: file changed since last read.`
- `Task completed.`

### Avoid
Avoid messages that are:

- apologetic without adding information
- vague about cause
- overly conversational
- overloaded with multiple ideas in one sentence

Less preferred:

- `Oops, something went wrong while trying to handle your request.`

Preferred:

- `Turn failed: model backend returned invalid event stream.`

## Consistency contract

## 1. Command behavior

### Help and usage
Command help should consistently provide:

- what the command does
- the most important arguments and options
- defaults when they matter
- constraints when they matter
- a short example where useful

Help text should describe observable behavior, not internal implementation details, unless the command is explicitly developer-facing.

### Successful command completion
A successful command should make the main outcome obvious.

Where practical:

- start with the result
- follow with supporting details only if they add value
- avoid burying the outcome after long explanation

### Partial success
If an operation partly succeeds, say so directly.

Do not present partial success as total success.

Preferred pattern:

- `Completed with warnings.`
- followed by specific details

### Failure
Failure messages should consistently answer:

- what failed
- why it failed, if known
- whether the user can retry
- what the user should change, if applicable

## 2. Message classes

The CLI should treat these message classes distinctly:

### Informational
For normal state and result reporting.

Examples:

- command completed
- session loaded
- task started

### Progress
For in-flight work.

Progress should be lightweight and should not drown out final results.

Examples:

- `Progress: generating`
- `Progress: running tool Read`

### Warning
For non-fatal issues, degraded behavior, or risks.

Warnings should make clear that execution continued.

Examples:

- truncated output
- fallback behavior
- unsupported optional feature

### Error
For failed operations.

Errors should be explicit and preferably single-purpose.

### Prompt/action-required
For situations where user input or approval is required.

These must stand out from passive information, even in plain text.

Examples:

- permission approvals
- missing required argument in interactive mode
- trust or confirmation prompts

## 3. Interaction flow

### Prompt only when needed
Interactive prompts should appear only when required to continue or when they materially improve safety.

Do not interrupt flow for low-value confirmations.

### Ask concrete questions
Prompts should ask one concrete thing at a time.

Good:

- `Allow command in workspace? [y/N]`

Less good:

- `Do you want to proceed with this potentially important operation that may affect files?`

### Show context before requesting action
Before asking for approval or confirmation, show enough context for the user to decide.

At minimum, when relevant, show:

- action type
- target resource
- important flags or scope
- consequence of approval

### Defaults should be safe
Interactive defaults should be conservative for destructive or trust-sensitive operations.

## 4. Terminal output structure

This contract allows light structure, not heavy ornament.

### Recommended hierarchy
When output needs structure, prefer this order:

1. primary result or current state
2. essential details
3. optional supporting details
4. next step or required action

### Labels
Use labels sparingly and consistently.

Useful labels include:

- `Progress:`
- `Warning:`
- `Error:`
- `Next:`

Do not invent many near-duplicate labels.

### Sections
Use sections only when output is large enough to benefit from them.

For small outputs, a single short block is better than section overhead.

### Dense output
If output is intended for program-adjacent reading, prefer stable field-like formatting over prose-heavy paragraphs.

Examples:

- `turn-started turn_id=1`
- `assistant: Echo: hello`
- `task_id=abc123 status=running`

## 5. Runtime event presentation

Because Pinser already exposes typed runtime events, the CLI should preserve a stable visual distinction between event categories.

At minimum, user-facing event output should make it easy to distinguish:

- lifecycle events
- user content
- assistant content
- progress updates
- tool-related activity

The exact rendering may evolve, but a single mixed undifferentiated stream should be avoided.

### Event naming
Prefer stable, low-ambiguity names for lifecycle events.

Examples:

- `turn-started`
- `turn-completed`
- `turn-cancelled`
- `turn-failed`

Prefer one canonical term for each state instead of multiple synonyms.

## 6. Error and warning contract

### Errors must be actionable when possible
If the cause is known, tell the user what to change.

Examples:

- `Error: path must be absolute.`
- `Error: file update blocked because the file was not fully read in this session.`
- `Error: command denied by permission policy.`

### Distinguish user error from system failure
Where possible, use different wording for:

- invalid input
- permission denial
- environmental failure
- internal bug
- unavailable feature

This helps users understand whether retrying makes sense.

### Do not overexpose internals by default
Tracebacks, raw exceptions, and internal implementation details should not be the default user-facing path.

If exposed, they should be behind a debug or developer-oriented mode.

## 7. Naming and terminology

Use one term consistently for each concept.

Prefer stable project terms such as:

- session
- turn
- task
- tool
- permission
- workspace
- model
- event

Avoid switching terms casually, such as using `job`, `run`, and `task` interchangeably unless the system intentionally distinguishes them.

## 8. Accessibility and robustness

The CLI should remain understandable when:

- color is disabled
- terminal width is narrow
- output is redirected to a file
- output is read after the fact rather than live

Contributors should prefer:

- plain text first
- readable wrapping behavior
- stable punctuation and separators
- moderate line lengths where practical

ASCII-safe output is preferred unless there is a clear reason to require more.

## 9. Change policy

This contract is intentionally lightweight.

Contributors may deviate when:

- a new feature needs a better pattern
- a safety requirement demands clearer output
- a typed runtime contract suggests a more durable presentation model
- a future TUI layer creates a better separation between machine-like event streams and human-focused summaries

When deviating, preserve the core principles:

- technical precision
- consistency
- visible state
- explicit safety signals
- plain-terminal robustness

## Practical checklist for contributors

Before adding or changing CLI output, check:

- Is the wording technical and precise?
- Is the main outcome obvious?
- Is it clear whether this is info, progress, warning, error, or action-required?
- Does the message expose important safety implications?
- Will the output still make sense without color?
- Is the terminology consistent with existing project concepts?
- Is the formatting simple enough to reuse elsewhere?

## Bottom line

Pinser's current UI contract is intentionally modest.

The CLI should feel consistent, technical, and operationally clear. It should favor predictable output, explicit state, and unambiguous safety messaging over personality or decorative formatting.
