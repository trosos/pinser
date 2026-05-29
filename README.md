# Pinser

Pinser is a [vibe trash](./HUMANS.txt).

If/when ready, it will be a free-software alternative for Claude Code-style workflows.

The project aims to provide a user-controlled, inspectable alternative for terminal coding workflows while remaining independently developed.

## Status

Pinser is in an early stage, but it has moved past the initial runtime skeleton.

Current roadmap status:

- Phase 0: complete
- Phase 1: complete
- Phase 2: complete
- Phase 2.1: complete
- Phase 3: next planned implementation focus

Today the project has a usable local-runtime baseline with core local tools, an initial permission engine, and post-Phase-2 hardening for tool validation, path safety, output budgeting, untrusted tool-output framing, and Bash subprocess safety.

The next major milestone is Phase 3: transcript persistence, resume, and recovery basics.

## What Pinser is trying to do

- provide a free-software alternative for Claude Code-style workflows
- support useful terminal coding workflows
- support documented and user-accessible APIs
- make any support for undocumented APIs, if present, explicitly opt-in
- provide local or public-API-based workarounds when undocumented features are unavailable

## Current implementation snapshot

Today the repository includes:

- a Python project bootstrap with `uv`, `pytest`, `ruff`, and `mypy`
- a Typer-based CLI
- configuration loading for workspace-local state
- a typed runtime kernel with:
  - typed `SessionState` and `TurnState`
  - structured prompt assembly
  - typed runtime events for user, assistant, progress, lifecycle, and tool activity
  - a fake model backend for deterministic tests
  - a headless runtime facade and a one-turn CLI command
- core local tools and supporting safety/runtime behavior:
  - `Read`, `Edit`, `FileWrite`, `Glob`, `Grep`, and `Bash`
  - an initial permission engine and approval-mode handling
  - workspace/path safety checks and protected-path enforcement
  - read-before-write and stale-read protections for file mutation
  - bounded tool outputs and prompt-facing framing of tool output as tool-produced, untrusted content
  - reduced-environment and timeout-cleanup hardening for Bash

Still intentionally out of scope at this stage:

- transcript persistence and resume
- advanced retry/fallback behavior
- PowerShell parity work
- notebook-aware mutation support
- MCP integration
- multi-agent delegation/orchestration
- remote/API-backed operation
- user-visible background shell task identity and lifecycle

## API support

Pinser is intended to work primarily with supported public APIs and local implementations where possible.

Some optional features may depend on undocumented APIs. If such support exists, it should be treated as experimental, explicitly enabled by the user, and not considered part of the default Pinser experience.

## If undocumented APIs are not used

When users do **not** opt into undocumented APIs, Pinser should prefer public APIs and local substitutes.

Examples include:

- calling supported public APIs directly
- supporting other compatible model providers
- using local subprocesses for worker execution
- storing session and task state locally
- providing similar convenience features with local tooling such as git and ripgrep
- degrading gracefully when exact compatibility is impossible

## Installation

Current development setup uses Python and `uv`.

Minimum requirements:

- Python 3.12 or newer
- `uv` available on `PATH` or invokable explicitly

One workable setup flow is:

```bash
uv sync --extra dev
uv run pinser main --workspace .
```

If `uv` is not on your `PATH`, you may need to invoke it explicitly, for example:

```bash
~/.local/bin/uv sync --extra dev
~/.local/bin/uv run pinser main --workspace .
```

## Useful commands

Run the full verification suite:

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

Run the minimal CLI bootstrap:

```bash
uv run pinser main --workspace .
```

Run one minimal runtime turn:

```bash
uv run pinser run-turn hello --workspace .
```

The current default CLI backend is a built-in deterministic echo backend rather than a real LLM integration or a tool-planning dummy backend.

So the stock `run-turn` command currently produces an echo-style turn like this:

```text
turn-started turn_id=1 user=hello
user: hello
Progress: generating
assistant: Echo: hello
turn-completed turn_id=1
```

The runtime and tests already support local tool execution and tool events for `Read`, `Edit`, `FileWrite`, `Glob`, `Grep`, and `Bash`, but that tool-capable path is not yet exposed through the default CLI behavior.

## Contributing / developer docs

If you want implementation details, architecture notes, or rewrite guidance, see [HACKING.md](./HACKING.md) and [docs/project-roadmap.md](./docs/project-roadmap.md).

## Disclaimer

Pinser is an independent project. It is not affiliated with, endorsed by, or supported by Anthropic.

Any optional support for undocumented APIs, if added, is experimental and provided strictly as a user-enabled compatibility path, not as the recommended default. Such use may be unstable, may stop working without notice, and may be subject to provider terms and restrictions.
