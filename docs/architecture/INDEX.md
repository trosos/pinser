# Architecture Documentation Index

This index is a reader-oriented map of the architecture documentation in this directory.

It is intended to help a new reader answer three questions quickly:

1. **Where should I start?**
2. **Which document is authoritative for a given subsystem?**
3. **What should I read next for implementation of a specific area?**

This document is a navigation aid, not a normative specification. When in doubt, the subsystem documents themselves are authoritative.

## Recommended reading paths

### If you are new to the project
Read in this order:

1. [`hld.md`](./hld.md) — top-level architecture, major runtime concepts, and system shape
2. [`feature-prioritization.md`](./feature-prioritization.md) — what matters most for a rebuild, and what can wait
3. [`interfaces-and-endpoints.md`](./interfaces-and-endpoints.md) — main surfaces exposed by the system
4. [`tool-contracts.md`](./tool-contracts.md) — tool model, execution contracts, and core tool behaviors
5. [`permission-engine.md`](./permission-engine.md) — approval model and enforcement rules
6. [`transcript-and-persistence-semantics.md`](./transcript-and-persistence-semantics.md) — durable record, event semantics, and state reconstruction
7. [`session-compaction-and-recovery.md`](./session-compaction-and-recovery.md) — compaction, recovery, and resume behavior

### If you are implementing the local interactive runtime
Start with:

- [`hld.md`](./hld.md)
- [`interfaces-and-endpoints.md`](./interfaces-and-endpoints.md)
- [`turn-failure-and-retry-state-machine.md`](./turn-failure-and-retry-state-machine.md)
- [`model-and-request-shaping.md`](./model-and-request-shaping.md)
- [`message-normalization-for-api.md`](./message-normalization-for-api.md)

Then read:

- [`tool-contracts.md`](./tool-contracts.md)
- [`tool-input-streaming-and-partial-assembly.md`](./tool-input-streaming-and-partial-assembly.md)
- [`tool-result-budgeting-and-dedup.md`](./tool-result-budgeting-and-dedup.md)

### If you are implementing permissions and shell execution safety
Start with:

- [`permission-engine.md`](./permission-engine.md)
- [`bash-and-powershell-safety.md`](./bash-and-powershell-safety.md)
- [`path-and-filesystem-safety.md`](./path-and-filesystem-safety.md)
- [`implementation-notes-and-gotchas.md`](./implementation-notes-and-gotchas.md)

### If you are implementing persistence, resume, and recovery
Start with:

- [`transcript-and-persistence-semantics.md`](./transcript-and-persistence-semantics.md)
- [`session-compaction-and-recovery.md`](./session-compaction-and-recovery.md)
- [`conversation-recovery-state-machine.md`](./conversation-recovery-state-machine.md)
- [`agent-resume-and-sidechains.md`](./agent-resume-and-sidechains.md)

### If you are implementing tasks, teams, and coordinated worker execution
Start with:

- [`task-and-swarm.md`](./task-and-swarm.md)
- [`agent-steering-and-work-coordination.md`](./agent-steering-and-work-coordination.md)
- [`agent-resume-and-sidechains.md`](./agent-resume-and-sidechains.md)
- [`interfaces-and-endpoints.md`](./interfaces-and-endpoints.md)
- [`tool-contracts.md`](./tool-contracts.md)

### If you are implementing remote / API-backed operation
Start with:

- [`remote-api.md`](./remote-api.md)
- [`remote-bridge-session-lifecycle.md`](./remote-bridge-session-lifecycle.md)
- [`message-normalization-for-api.md`](./message-normalization-for-api.md)
- [`interfaces-and-endpoints.md`](./interfaces-and-endpoints.md)

### If you are implementing model routing and request shaping
Start with:

- [`model-selection-and-routing.md`](./model-selection-and-routing.md)
- [`model-and-request-shaping.md`](./model-and-request-shaping.md)
- [`message-normalization-for-api.md`](./message-normalization-for-api.md)

## Documentation map by subsystem

## 1. System overview and implementation planning

### [`hld.md`](./hld.md)
**Primary role:** top-level architecture overview.

Read this first to understand:
- core runtime structure
- major responsibilities of the system
- principal data and control flows
- how the major subsystems fit together

### [`feature-prioritization.md`](./feature-prioritization.md)
**Primary role:** implementation sequencing and delivery prioritization.

Use this to understand:
- what is core to the product
- what is important but can be deferred
- what should not dominate early rebuild effort

### [`implementation-notes-and-gotchas.md`](./implementation-notes-and-gotchas.md)
**Primary role:** cross-cutting cautions and non-obvious behavior.

Use this when implementation details seem ambiguous or deceptively simple.

## 2. Interfaces, request shaping, and turn execution

### [`interfaces-and-endpoints.md`](./interfaces-and-endpoints.md)
**Primary role:** external and internal system surfaces.

Use this to understand:
- the main interfaces exposed by the product
- endpoint-level responsibilities
- session/task/worker-related surface area

### [`model-and-request-shaping.md`](./model-and-request-shaping.md)
**Primary role:** how requests are assembled and projected for the model.

Use this to understand:
- prompt/request composition
- message packaging
- model-facing payload construction
- the relationship between internal history and model input

### [`message-normalization-for-api.md`](./message-normalization-for-api.md)
**Primary role:** normalization rules for API-safe message representation.

Use this to understand:
- conversion of internal conversational state to provider/API format
- normalization constraints and compatibility behavior

### [`turn-failure-and-retry-state-machine.md`](./turn-failure-and-retry-state-machine.md)
**Primary role:** control flow for failures, retries, and fallback behavior.

Use this to understand:
- what happens when a turn fails
- when and how retry paths differ
- how the runtime returns to a stable state

## 3. Tool system and tool execution behavior

### [`tool-contracts.md`](./tool-contracts.md)
**Primary role:** main reference for tool semantics and contracts.

This is the central document for:
- tool invocation and result semantics
- core local tools
- agent/task-oriented tools
- resource and bridge-related tools
- success/error contract expectations

### [`tool-input-streaming-and-partial-assembly.md`](./tool-input-streaming-and-partial-assembly.md)
**Primary role:** handling of streamed tool input and incomplete argument assembly.

Use this to understand:
- partial tool-call collection
- assembly timing
- validation boundaries
- execution readiness conditions

### [`tool-result-budgeting-and-dedup.md`](./tool-result-budgeting-and-dedup.md)
**Primary role:** tool-result shaping for display, persistence, and token economy.

Use this to understand:
- budgeting of result content
- de-duplication behavior
- how to avoid repeated or overlarge tool result payloads

## 4. Permissioning and execution safety

### [`permission-engine.md`](./permission-engine.md)
**Primary role:** approval model and decision engine.

This is the main authority for:
- when approval is required
- how approval policies are evaluated
- how execution requests are classified
- how approval outcomes affect runtime behavior

### [`bash-and-powershell-safety.md`](./bash-and-powershell-safety.md)
**Primary role:** shell execution safety rules and command-hardening behavior.

Use this to understand:
- shell invocation constraints
- risk classification
- command construction expectations
- execution-time guardrails

### [`path-and-filesystem-safety.md`](./path-and-filesystem-safety.md)
**Primary role:** path normalization and filesystem boundary enforcement.

Use this to understand:
- allowed path behavior
- normalization and traversal prevention
- workspace boundary handling
- file-operation safety expectations

## 5. Persistence, transcript semantics, compaction, and recovery

### [`transcript-and-persistence-semantics.md`](./transcript-and-persistence-semantics.md)
**Primary role:** durable event/transcript model.

This is the main reference for:
- what is recorded
- what is considered canonical state
- how state is reconstructed from persisted records
- event semantics and transcript invariants

### [`session-compaction-and-recovery.md`](./session-compaction-and-recovery.md)
**Primary role:** compaction and resume mechanics.

Use this to understand:
- how long-running sessions are compacted
- how summaries/checkpoints interact with replay
- how execution resumes after truncation or restart

### [`conversation-recovery-state-machine.md`](./conversation-recovery-state-machine.md)
**Primary role:** recovery control flow for broken or interrupted conversations.

Use this to understand:
- recovery phases
- decision points during restoration
- restart/resume progression

## 6. Agents, sidechains, and coordinated work

### [`agent-resume-and-sidechains.md`](./agent-resume-and-sidechains.md)
**Primary role:** sidechain/session branching and agent continuation behavior.

Use this to understand:
- agent resume semantics
- sidechain creation and lifecycle
- parent/child conversational relationships
- resumed work context boundaries

### [`agent-steering-and-work-coordination.md`](./agent-steering-and-work-coordination.md)
**Primary role:** work delegation and steering behavior across coordinated actors.

Use this to understand:
- steering patterns
- worker direction and control
- coordination semantics beyond a single turn loop

### [`task-and-swarm.md`](./task-and-swarm.md)
**Primary role:** tasks, teams, swarms, and worker orchestration.

This is the main entry point for:
- task lifecycle
- team and swarm concepts
- coordination roles and execution modes
- how shared or parallelized work is organized

## 7. Model selection and routing

### [`model-selection-and-routing.md`](./model-selection-and-routing.md)
**Primary role:** model choice and routing policy.

Use this to understand:
- how the runtime selects providers/models
- routing constraints
- fallback and capability-based selection logic

## 8. Remote and bridge-backed operation

### [`remote-api.md`](./remote-api.md)
**Primary role:** remote/API-backed behavior and contract surface.

Use this to understand:
- the remote execution model
- request/response behavior for remote operation
- remote-specific compatibility expectations

### [`remote-bridge-session-lifecycle.md`](./remote-bridge-session-lifecycle.md)
**Primary role:** bridge lifecycle and session state when operating through a remote bridge.

Use this to understand:
- remote bridge startup and teardown
- session ownership and continuity across the bridge
- lifecycle events specific to remote-backed operation

## Cross-reference guide

Use this section when a change touches more than one subsystem.

### Implementing a new tool
Read:
- [`tool-contracts.md`](./tool-contracts.md)
- [`tool-input-streaming-and-partial-assembly.md`](./tool-input-streaming-and-partial-assembly.md)
- [`tool-result-budgeting-and-dedup.md`](./tool-result-budgeting-and-dedup.md)
- [`permission-engine.md`](./permission-engine.md)
- [`path-and-filesystem-safety.md`](./path-and-filesystem-safety.md) if the tool touches files

### Changing shell execution behavior
Read:
- [`bash-and-powershell-safety.md`](./bash-and-powershell-safety.md)
- [`permission-engine.md`](./permission-engine.md)
- [`path-and-filesystem-safety.md`](./path-and-filesystem-safety.md)
- [`implementation-notes-and-gotchas.md`](./implementation-notes-and-gotchas.md)

### Changing persistence or replay behavior
Read:
- [`transcript-and-persistence-semantics.md`](./transcript-and-persistence-semantics.md)
- [`session-compaction-and-recovery.md`](./session-compaction-and-recovery.md)
- [`conversation-recovery-state-machine.md`](./conversation-recovery-state-machine.md)
- [`agent-resume-and-sidechains.md`](./agent-resume-and-sidechains.md)

### Changing agent/task/swarm behavior
Read:
- [`task-and-swarm.md`](./task-and-swarm.md)
- [`agent-steering-and-work-coordination.md`](./agent-steering-and-work-coordination.md)
- [`agent-resume-and-sidechains.md`](./agent-resume-and-sidechains.md)
- [`tool-contracts.md`](./tool-contracts.md)
- [`interfaces-and-endpoints.md`](./interfaces-and-endpoints.md)

### Changing model request formation or provider compatibility
Read:
- [`model-and-request-shaping.md`](./model-and-request-shaping.md)
- [`message-normalization-for-api.md`](./message-normalization-for-api.md)
- [`model-selection-and-routing.md`](./model-selection-and-routing.md)
- [`turn-failure-and-retry-state-machine.md`](./turn-failure-and-retry-state-machine.md)

### Changing remote-backed execution
Read:
- [`remote-api.md`](./remote-api.md)
- [`remote-bridge-session-lifecycle.md`](./remote-bridge-session-lifecycle.md)
- [`interfaces-and-endpoints.md`](./interfaces-and-endpoints.md)
- [`message-normalization-for-api.md`](./message-normalization-for-api.md)

## Fast lookup table

| Need | Start here |
|---|---|
| Understand the whole system | [`hld.md`](./hld.md) |
| Know what to build first | [`feature-prioritization.md`](./feature-prioritization.md) |
| Understand interfaces/endpoints | [`interfaces-and-endpoints.md`](./interfaces-and-endpoints.md) |
| Implement tools | [`tool-contracts.md`](./tool-contracts.md) |
| Handle partial/streamed tool inputs | [`tool-input-streaming-and-partial-assembly.md`](./tool-input-streaming-and-partial-assembly.md) |
| Budget/deduplicate tool results | [`tool-result-budgeting-and-dedup.md`](./tool-result-budgeting-and-dedup.md) |
| Implement approvals | [`permission-engine.md`](./permission-engine.md) |
| Make shell execution safe | [`bash-and-powershell-safety.md`](./bash-and-powershell-safety.md) |
| Enforce filesystem safety | [`path-and-filesystem-safety.md`](./path-and-filesystem-safety.md) |
| Understand transcript persistence | [`transcript-and-persistence-semantics.md`](./transcript-and-persistence-semantics.md) |
| Implement session compaction/recovery | [`session-compaction-and-recovery.md`](./session-compaction-and-recovery.md) |
| Implement conversation recovery | [`conversation-recovery-state-machine.md`](./conversation-recovery-state-machine.md) |
| Implement agent resume/sidechains | [`agent-resume-and-sidechains.md`](./agent-resume-and-sidechains.md) |
| Implement tasks/teams/swarms | [`task-and-swarm.md`](./task-and-swarm.md) |
| Implement worker steering | [`agent-steering-and-work-coordination.md`](./agent-steering-and-work-coordination.md) |
| Implement model routing | [`model-selection-and-routing.md`](./model-selection-and-routing.md) |
| Build model-facing requests | [`model-and-request-shaping.md`](./model-and-request-shaping.md) |
| Normalize conversation state for APIs | [`message-normalization-for-api.md`](./message-normalization-for-api.md) |
| Understand retry/failure flow | [`turn-failure-and-retry-state-machine.md`](./turn-failure-and-retry-state-machine.md) |
| Implement remote/API-backed mode | [`remote-api.md`](./remote-api.md) |
| Implement remote bridge lifecycle | [`remote-bridge-session-lifecycle.md`](./remote-bridge-session-lifecycle.md) |
| Check cross-cutting caveats | [`implementation-notes-and-gotchas.md`](./implementation-notes-and-gotchas.md) |

## Suggested maintenance rule

When adding a new architecture document:

1. add it to the relevant subsystem section above
2. add at least one entry in the fast lookup table if it is a primary reference
3. update one or more recommended reading paths if it changes onboarding order
4. prefer linking from this index rather than duplicating subsystem summaries elsewhere
