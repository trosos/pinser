# Threat model

This document gives a short, implementation-oriented threat model for Pinser based on the current architecture docs.

## Scope and assumptions

In scope:
- the local CLI/runtime
- model-driven tool execution
- filesystem access and mutation
- transcript/session persistence
- background tasks and teammate/swarm execution
- optional remote HTTP integrations
- MCP and bridge-style integrations

Assumptions:
- Pinser is primarily a local, user-controlled coding agent
- some features may later support undocumented remote APIs, but those are optional and should stay explicitly opt-in
- the model, remote services, MCP servers, fetched web content, and persisted transcript data must all be treated as potentially untrusted inputs

## Key assets

- user source code and workspace contents
- secrets in files, environment variables, tokens, and config
- local machine integrity and shell execution boundary
- session transcripts, tool outputs, and task state
- permission settings and other Pinser-owned configuration
- remote session identity and OAuth credentials when enabled

## Trust boundaries

Main trust boundaries identified in the docs:
- model output -> runtime actions
- user workspace -> Pinser internal state under `.pinser/`
- local runtime -> shell / subprocess execution
- local runtime -> remote APIs
- local runtime -> MCP servers and bridge/socket peers
- persisted transcripts/tool outputs -> resumed live session state
- leader agent -> teammate/subagent workers

## Primary threats

### 1. Unsafe model-to-action execution
The model can attempt dangerous file edits, shell commands, remote actions, or teammate instructions.

Risks:
- destructive filesystem writes
- command execution with unexpected side effects
- privilege expansion via delegated workers or background tasks
- abuse of remote-trigger style features

Relevant controls from the docs:
- explicit per-tool permission engine with allow/deny/ask modes
- read-only/destructive tool classification
- read-before-write and stale-read checks for file mutation
- shell safety rules, sandbox routing, and background-task controls
- restricted tool visibility and per-mode tool filtering

### 2. Filesystem escape and path-based attacks
Attackers may try to use symlinks, traversal, UNC/network paths, special files, or case tricks to escape workspace policy or access sensitive files.

Risks:
- editing protected config such as `.pinser/`, `.git/`, shell profiles, or secrets
- credential leakage from UNC/SMB/WebDAV probing
- hangs or unexpected behavior from device/special files
- bypassing scope checks through symlinks or platform-specific path syntax

Relevant controls:
- dual checking of lexical and resolved paths
- built-in protected-path rules for config-sensitive directories/files
- UNC/network hardening before filesystem probing
- special-file blocking and suspicious Windows path detection
- case-insensitive protected-path comparison and normalized containment checks

### 3. Transcript poisoning and unsafe resume
Persisted transcripts and tool-result artifacts are later used to reconstruct session state.
If that state is malformed or attacker-controlled, resume could reintroduce unsafe actions or invalid history.

Risks:
- replay of malformed tool-use/tool-result pairs
- corrupted session metadata or resumed context
- prompt injection through persisted tool output or fetched content
- remote hydration importing incomplete or hostile state

Relevant controls:
- resume as a normalization/repair pipeline, not raw replay
- validation/sanitization of persisted enum-like fields
- filtering unresolved tool uses and orphaned content
- separation of durable transcript entries from ephemeral progress state
- hydrate-before-continue behavior for remote sessions

### 4. Untrusted external content influencing the model
Web fetch/search results, MCP resources, remote responses, and teammate messages can all carry adversarial instructions.

Risks:
- prompt injection causing bad tool use
- data exfiltration via subsequent tool calls
- unsafe follow-up actions triggered by search/fetch results
- misleading citations or remote instructions

Relevant controls:
- keep external content as untrusted data
- preserve user-approval gates for powerful tools
- keep tool contracts strict and typed
- maintain separation between fetched content and authority to act

### 5. Multi-agent and background-task abuse
Delegated workers and teammates widen the attack surface and can create indirect privilege escalation paths.

Risks:
- a worker acting with broader permissions than intended
- spoofed or malformed control messages
- hard-to-audit side effects from background tasks
- delivery to stopped agents causing unsafe auto-resume behavior

Relevant controls:
- backend-neutral but explicit spawn/send/terminate/kill lifecycle
- structured control-message protocol for shutdown/approval flows
- app-state-visible runtime task tracking and stable task IDs
- team deletion guards and durable shared task ownership semantics
- permission context passed into teammate spawn

### 6. Remote integration and credential risk
Optional remote sessions, environments, and trigger APIs introduce network and token-handling risks.

Risks:
- token misuse or leakage
- accidental dependence on undocumented/internal APIs
- SSRF-like or unauthorized remote trigger usage
- trust confusion between local-safe and remote-capable modes

Relevant controls:
- remote features gated by feature flags/policy
- explicit OAuth + organization UUID requirements
- endpoint-specific validation and bounded retry rules
- default preference for local/public-API operation
- documented opt-in posture for undocumented API support

## Highest-priority security requirements

1. **Never let model output directly bypass tool permissions.**
2. **Preserve path safety and UNC hardening exactly; do not reduce checks to string-prefix matching.**
3. **Keep read-before-write and stale-read protections for all mutation tools.**
4. **Treat transcripts, remote data, MCP content, and web content as untrusted on resume and during prompt assembly.**
5. **Keep strong separation between user workspace data and Pinser-owned config/state under `.pinser/`.**
6. **Ensure delegated workers receive explicit, scoped permission context and auditable lifecycle tracking.**
7. **Make undocumented remote features opt-in and clearly distinguish them from the default local/public-API path.**

## Recommended near-term mitigations

As implementation continues, prioritize:
- threat-focused tests for path validation, symlink handling, and protected-path enforcement
- tests for transcript recovery from malformed or partially written state
- tests that prompt-injection content cannot directly cause unsafe tool execution without policy approval
- explicit redaction/handling rules for secrets in logs, transcripts, and persisted tool outputs
- audit logging for destructive tool calls and remote-trigger usage
- clear UX indicators when the runtime is using remote or undocumented integrations

## Out of scope for this short model

This document does not attempt a full STRIDE analysis, formal cryptographic review, or supply-chain review of dependencies. It is a practical starting point for early implementation and test planning.