# Implementation stack decision

This document records the recommended implementation stack for the first Pinser implementation.

It is intended as a planning aid for developers and architects, separate from the current architecture notes in `docs/architecture/`.

## Normative TL;DR

Unless there is an explicit, documented exception, the first Pinser implementation should use:

- **Python 3.13** as the target runtime, with **Python 3.12** as the lowest acceptable fallback
- **strong static typing**, enforced in CI
- an **async-first core** built on `asyncio`
- a **framework-light core runtime**, not a heavyweight application framework
- **`Typer`** for CLI structure
- **`pydantic` v2** for configuration and external boundary validation
- **`httpx`** for outbound HTTP
- **local files plus SQLite** for initial persistence
- **standard-library subprocess primitives** for command execution
- **`pytest` + `pytest-asyncio` + `ruff` + one type checker** as required quality tools
- **`uv`** for development workflow and dependency management

Unless runtime needs prove otherwise, developers should also follow these constraints:

- keep the core implementation mostly standard-library driven
- keep persistence concerns separated rather than building one generic store
- defer rich TUI work until the runtime kernel is stable
- defer web-framework adoption until remote/API surfaces are actually implemented
- avoid a heavy ORM in the first implementation

## Decision summary

For the first implementation, Pinser should use:

- **Language:** Python 3.13+ (acceptable floor: Python 3.12 if ecosystem constraints require it)
- **Typing stance:** strongly typed Python, with type checking enforced in CI
- **Core application style:** async-first modular application, primarily standard-library-driven
- **CLI framework:** `Typer`
- **Terminal UI:** start with a plain CLI/repl-style interface; add `Textual` only when richer TUI behavior is needed
- **Data validation/config models:** `pydantic` v2
- **HTTP client/server:** `httpx` for outbound HTTP, `FastAPI` only for remote/API surfaces when those are implemented
- **Persistence (initial):** local files plus SQLite from the standard library
- **Process execution:** `asyncio.subprocess` and standard library process primitives
- **Notebook support:** JSON-based handling first; add `nbformat` when notebook editing becomes active work
- **Testing:** `pytest`, `pytest-asyncio`
- **Lint/format:** `ruff`
- **Static typing:** `mypy` or `pyright`; prefer `pyright` if the team wants stricter developer feedback, otherwise `mypy` for simpler packaging
- **Packaging/build:** `uv` for development workflow and dependency management

## Why Python

Python is a good fit for this project’s first implementation because the documented system is:

- orchestration-heavy rather than numerics-heavy
- built around async streaming, subprocess control, persistence, and protocol adaptation
- expected to integrate with shell tools, git, local filesystems, and external APIs
- likely to benefit from rapid iteration while the clean-room architecture is still settling

Python is especially strong for:

- process orchestration
- filesystem and shell integration
- JSON and protocol-heavy systems
- local tooling ecosystems such as LSP clients, notebook tooling, and SQLite-backed state
- readable implementation of state machines and adapters

The architecture docs also point toward a system where correctness of boundaries matters more than raw CPU throughput. That generally favors a language with fast iteration and a strong ecosystem for glue code.

## Why not avoid Python

I do **not** currently have a strong reason to argue against Python for the first implementation.

A language like Rust could offer stronger compile-time guarantees for permission enforcement, process isolation boundaries, and concurrency structure. A language like TypeScript could feel closer to the architecture source material. But both would impose more upfront implementation cost for a clean-room rewrite that still needs to discover its final internal interfaces.

For a first implementation, the main risks are architectural correctness, safety policy correctness, and maintainability—not raw performance. Python is a reasonable choice if we compensate with disciplined typing, testing, and narrow interfaces.

## Recommended stack in more detail

## 1. Language baseline

Recommendation:

- target **Python 3.13** if practical
- allow **Python 3.12** as the minimum if dependency support or packaging friction appears

Rationale:

- modern typing support is materially better than in older Python versions
- `asyncio` is mature and suitable for the runtime model described in the docs
- `sqlite3`, `pathlib`, `subprocess`, `asyncio`, `json`, and `dataclasses` already cover a large part of the required runtime

Avoid targeting older Python versions unless there is a strong distribution requirement.

## 2. Typing policy

Recommendation:

- treat type hints as part of the design, not optional decoration
- enforce type checking in CI
- prefer `Protocol`, `TypedDict`, `Literal`, `Enum`, `dataclass`, and small typed service interfaces
- keep the core runtime and policy code fully typed

Suggested policy:

- no untyped defs in core runtime packages
- no `Any` in safety-critical code without a comment justifying it
- use `pydantic` at input boundaries and typed domain models internally

Rationale:

The documented architecture has many boundary-heavy subsystems:

- tool contracts
- permission decisions
- transcript events
- model-routing decisions
- task coordination messages

Those are exactly the areas where typed Python helps prevent drift and accidental shape mismatches.

## 3. Overall framework choice

Recommendation:

- use **no heavyweight application framework** for the core runtime
- structure the code as a set of modules/services around `asyncio`

Rationale:

The project is not primarily a web app. Its center of gravity is:

- a conversation runtime kernel
- async event streaming
- local tool execution
- persistence/resume logic
- multi-agent/task orchestration

A heavyweight framework would mostly add indirection. The core should instead be ordinary Python packages with explicit interfaces.

## 4. CLI and interactive entrypoints

Recommendation:

- use `Typer` for command-line structure
- keep the first interactive experience simple: line-oriented CLI or REPL
- defer a richer TUI until the runtime contracts stabilize

Why `Typer`:

- low ceremony
- good type-hint integration
- straightforward command decomposition
- friendlier than raw `argparse` for a tool expected to grow many subcommands/modes

Why defer full TUI work:

The docs emphasize runtime behavior and orchestration correctness, not terminal rendering. A richer TUI can be added after the kernel and tool model are stable.

If a richer terminal app is later needed, `Textual` is the best likely candidate because it supports structured async terminal applications better than ad hoc ANSI handling.

## 5. Data modeling and validation

Recommendation:

- use `pydantic` v2 at external and persistence boundaries
- use `dataclasses` or small classes for internal domain entities where validation is not needed on every construction

Use `pydantic` for:

- config files
- tool input schemas
- API payloads
- persisted transcript/event records when loaded from disk
- remote bridge/session payloads

Use lighter internal models for:

- in-memory runtime state
- event objects flowing inside the engine
- narrow policy objects

Rationale:

This split keeps boundaries robust without turning the whole runtime into validation-heavy object construction.

## 6. Async and concurrency model

Recommendation:

- use `asyncio` as the single concurrency model for the first implementation
- make async generators the native interface for event streaming
- define explicit cancellation scopes at the application level even if implemented with plain `asyncio` primitives first

Rationale:

This lines up directly with the architecture docs, which strongly suggest:

- async streaming as a core protocol
- overlapping background work under active latency
- cancellable turns and tasks
- subprocess-backed tools and workers

Avoid mixing concurrency systems unless there is a clear need.

## 7. Persistence strategy

Recommendation for initial implementation:

- store transcripts and task state in local files
- use SQLite for indexed/shared mutable state where atomicity matters
- keep persistence adapters separate for:
  - prompt history
  - transcript/session persistence
  - durable task coordination

Rationale:

The docs are explicit that these persistence responsibilities should remain separate. SQLite is a good fit for local durability and coordination without adding infrastructure. Local files are sufficient for append-oriented transcript and artifact storage.

One correction to watch carefully: do not collapse all state into one generic ORM model too early.

## 8. HTTP / remote surfaces

Recommendation:

- use `httpx` for client behavior
- introduce `FastAPI` only when implementing remote/API-backed operation
- keep remote transport adapters outside the core runtime package

Rationale:

The core product can and should be developed without assuming a web server framework. But when remote/session APIs appear, `FastAPI` gives a practical typed interface for JSON-heavy surfaces.

## 9. Subprocess and shell execution

Recommendation:

- use standard library subprocess support via `asyncio.create_subprocess_exec`
- prefer argument-vector execution over shell-string construction wherever possible
- isolate shell-safety policy from execution transport

Rationale:

This area is safety-sensitive. The implementation should keep:

- command classification
- permission decisions
- path checks
- actual process spawning

as separate layers, which is easier if the process layer stays close to the standard library.

## 10. Testing and quality gates

Recommendation:

- `pytest`
- `pytest-asyncio`
- `ruff` for linting and formatting
- `pyright` or `mypy` for static type checking
- property tests for parser/normalization/state-machine edges if useful later

Suggested CI gates for early development:

- formatting/lint clean
- type check clean
- unit tests for permission engine, transcript semantics, and tool contracts
- integration tests for subprocess execution and session resume

## 11. Suggested library posture

Default rule:

- prefer the standard library first
- add third-party libraries only when they clearly reduce complexity or improve correctness at a boundary

Good initial third-party set:

- `typer`
- `pydantic`
- `httpx`
- `pytest`
- `pytest-asyncio`
- `ruff`
- one type checker (`pyright` or `mypy`)
- optionally `textual` later
- optionally `nbformat` later

This keeps the first implementation auditable and easy to bootstrap.

## 12. Proposed repository structure

One plausible Python-oriented layout is:

```text
src/pinser/
  app/
    cli/
    startup/
    config/
  runtime/
    engine/
    events/
    model_routing/
    context/
  tools/
    builtins/
    mcp/
    shell/
    files/
  permissions/
  persistence/
    transcript/
    history/
    tasks/
  agents/
    local/
    inproc/
    remote/
  transports/
    headless/
    api/
    tui/
  testing/
```

This is only a directional layout suggestion, not a binding architecture.

## 13. Explicit decisions

### Chosen

- Python 3 as the first implementation language
- enforced typing as a project norm
- async-first core runtime
- minimal-framework core
- local-first persistence with files and SQLite
- defer heavyweight UI choices until runtime behavior stabilizes

### Explicitly deferred

- committing to a web framework before remote APIs are implemented
- committing to a rich terminal UI before the runtime kernel is validated
- introducing a heavy ORM
- introducing distributed infrastructure for the first implementation
- optimizing for high-throughput multi-user service deployment before local single-user correctness

## 14. Revisit triggers

Revisit this decision if one of the following becomes true:

- Python typing discipline proves insufficient for safety-critical code review
- process isolation or sandboxing requirements demand stronger systems-language components
- performance bottlenecks appear in transcript replay, compaction, or multi-agent orchestration
- the intended deployment target shifts from local-first tool to multi-tenant remote service
- a future parity target requires runtime characteristics that Python makes awkward

If that happens, the likely adjustment is not a full rewrite but selective use of a non-Python component for a narrow subsystem.

## Bottom line

Use **Python 3 with strong typing and an async-first, mostly standard-library architecture** for the first Pinser implementation.

That gives the project:

- fast iteration during architecture discovery
- a strong ecosystem for CLI, subprocesses, files, JSON, and HTTP
- readable implementations of the documented runtime and safety layers
- a practical path to local-first development without premature framework commitment
