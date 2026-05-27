# Pinser

Pinser is a [vibe trash](./HUMANS.txt).

If/when ready, it will be a free-software alternative for Claude Code-style workflows.

The project aims to provide a user-controlled, inspectable alternative for terminal coding workflows while remaining independently developed.

## Status

Pinser is in an early stage.

Phase 1 is now in place: the project has a typed runtime skeleton with session and turn state, prompt assembly, a fake model backend, async event streaming, cancellation handling, and a minimal CLI command that streams one turn's runtime events.

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
- a minimal runtime kernel with:
  - typed `SessionState` and `TurnState`
  - structured prompt assembly
  - typed runtime events for user, assistant, progress, and lifecycle states
  - a fake model backend for deterministic tests
  - a headless runtime facade and a one-turn CLI command

Still intentionally out of scope at this stage:

- real tool execution
- transcript persistence and resume
- advanced retry/fallback behavior
- remote/API-backed operation

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

Example output:

```text
turn-started turn_id=1 user=hello
user: hello
progress: generating
assistant: Echo: hello
turn-completed turn_id=1
```

## Contributing / developer docs

If you want implementation details, architecture notes, or rewrite guidance, see [HACKING.md](./HACKING.md).

## Disclaimer

Pinser is an independent project. It is not affiliated with, endorsed by, or supported by Anthropic.

Any optional support for undocumented APIs, if added, is experimental and provided strictly as a user-enabled compatibility path, not as the recommended default. Such use may be unstable, may stop working without notice, and may be subject to provider terms and restrictions.
