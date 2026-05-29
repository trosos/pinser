# Phase 2 omitted functionality register

This note records important functionality intentionally omitted from the first Phase 2 implementation.

For canonical project phase status, see [`docs/project-roadmap.md`](../project-roadmap.md).
It exists to keep Phase 2 conservative, reduce scope drift, and make later planning easier.
For deeper behavior and long-term intent, see the architecture documents and roadmap referenced below.

## Omitted from the first Phase 2 implementation

### PowerShell execution and Windows-specific shell safety

Status:

- deferred beyond Phase 2

What is omitted:

- PowerShell command execution
- PowerShell-specific parsing and safety classification
- provider-path and Windows-specific path safety behavior
- parity between Bash and PowerShell approval behavior

Why omitted now:

- `docs/phase2/scope.md` makes PowerShell optional and deferred for Phase 2
- the current Phase 2 shell slice only needs conservative Bash foreground execution

Planned roadmap placement:

- later than Phase 2; primarily aligns with Phase 4 hardening work

See:

- [`../architecture/bash-and-powershell-safety.md`](../architecture/bash-and-powershell-safety.md)
- [`./scope.md`](./scope.md)
- [`../project-roadmap.md`](../project-roadmap.md)

### Background shell task identity and lifecycle

Status:

- deferred beyond Phase 2

What is omitted:

- durable background task IDs
- background process lifecycle tracking
- stop/list/reattach semantics for shell jobs
- transcript and UI handling for long-running background shell activity

Why omitted now:

- Phase 2 only requires conservative foreground shell execution
- the roadmap explicitly keeps user-visible background shell lifecycle out of Phase 2 scope

Planned roadmap placement:

- later than Phase 2; likely with broader runtime robustness work in Phase 4 or later

See:

- [`../architecture/bash-and-powershell-safety.md`](../architecture/bash-and-powershell-safety.md)
- [`../architecture/interfaces-and-endpoints.md`](../architecture/interfaces-and-endpoints.md)
- [`./scope.md`](./scope.md)
- [`../project-roadmap.md`](../project-roadmap.md)

### Richer approval/permission modes

Status:

- deferred beyond the initial Phase 2 implementation

What is omitted:

- `acceptEdits`
- `plan`
- `auto`
- auto-mode dangerous-rule stripping/restoration
- classifier-assisted approval behavior

Why omitted now:

- the initial implementation only needs externally visible `default` and `dontAsk`
- `docs/phase2/scope.md` places richer permission-mode completeness later

Planned roadmap placement:

- primarily Phase 4

See:

- [`../architecture/permission-engine.md`](../architecture/permission-engine.md)
- [`./scope.md`](./scope.md)
- [`../project-roadmap.md`](../project-roadmap.md)

### Notebook editing

Status:

- deferred beyond Phase 2

What is omitted:

- notebook-aware mutation tools
- cell-structured edit semantics
- notebook-specific safety and validation

Why omitted now:

- `docs/phase2/scope.md` explicitly treats notebook editing as deferred work
- the roadmap says Phase 2 should fail clearly rather than provide notebook-safe mutation

Planned roadmap placement:

- later than Phase 2

See:

- [`./scope.md`](./scope.md)
- [`../project-roadmap.md`](../project-roadmap.md)

### MCP, remote execution, and multi-agent orchestration

Status:

- deferred beyond Phase 2

What is omitted:

- MCP integration
- remote tool execution or remote runtime surfaces
- multi-agent delegation/orchestration

Why omitted now:

- Phase 2 is scoped to core local tools and a local permission engine
- these capabilities are explicitly listed as deferred in the planning notes

Planned roadmap placement:

- later phases after the local runtime core is stable

See:

- [`./TODO.md`](./TODO.md)
- [`../project-roadmap.md`](../project-roadmap.md)

## Interpretation note

These omissions are intentional, not accidental gaps in the Phase 2 implementation.
Phase 2 remains complete once the conservative local tool/runtime surface, permission behavior, and safety checks are implemented and verified, even though the broader compatibility surface described in architecture docs remains deferred.
