# Pinser

Pinser is a [vibe trash](./HUMANS.txt).

If/when ready, it will be a free-software alternative for Claude Code-style workflows.

The project aims to provide a user-controlled, inspectable alternative for terminal coding workflows while remaining independently developed.

## Status

Pinser is in an early stage.

A Phase 0 Python bootstrap is now in place, including a minimal CLI, initial configuration loading, and baseline test/lint/type-check setup.

## What Pinser is trying to do

- provide a free-software alternative for Claude Code-style workflows
- support useful terminal coding workflows
- support documented and user-accessible APIs
- make any support for undocumented APIs, if present, explicitly opt-in
- provide local or public-API-based workarounds when undocumented features are unavailable

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
uv run pinser --workspace .
```

If `uv` is not on your `PATH`, you may need to invoke it explicitly, for example:

```bash
~/.local/bin/uv sync --extra dev
~/.local/bin/uv run pinser --workspace .
```

To run the Phase 0 verification checks:

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Contributing / developer docs

If you want implementation details, architecture notes, or rewrite guidance, see [HACKING.md](./HACKING.md).

## Disclaimer

Pinser is an independent project. It is not affiliated with, endorsed by, or supported by Anthropic.

Any optional support for undocumented APIs, if added, is experimental and provided strictly as a user-enabled compatibility path, not as the recommended default. Such use may be unstable, may stop working without notice, and may be subject to provider terms and restrictions.
