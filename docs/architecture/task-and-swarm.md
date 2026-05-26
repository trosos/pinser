# Task, swarm, and team coordination contract

This document consolidates the multi-agent and task-coordination behavior needed for a clean-room rewrite.

It complements:
- `docs/interfaces-and-endpoints.md`
- `docs/tool-contracts.md`
- `docs/agent-resume-and-sidechains.md`
- `docs/agent-steering-and-work-coordination.md`
- `docs/implementation-notes-and-gotchas.md`

It exists because task and swarm behavior is part of the compatibility surface, but the relevant details were previously spread across several documents.

Primary sources used for this consolidation:
- `docs/interfaces-and-endpoints.md`
- `docs/tool-contracts.md`
- `docs/hld.md`
- `docs/agent-resume-and-sidechains.md`
- `docs/agent-steering-and-work-coordination.md`

Where behavior below is stated as a preservation requirement, it is derived from already-verified contracts in those companion docs.
This document intentionally consolidates them into one implementation-facing reference.

---

## 1. Scope

This document covers the coordination layer for:
- runtime background tasks
- persistent shared task lists
- team/swarm lifecycle
- teammate execution backends
- mailbox/message semantics
- approval and shutdown coordination
- differences between in-process, pane-backed, and remote-style execution

It is not a duplicate of all lower-level tool docs.
Instead, it explains how those tools and interfaces fit together into one coherent orchestration model.

---

## 2. Two different task systems exist

A rewrite must preserve the distinction between two different concepts that are both called “task” in everyday language.

### 2.1 Runtime background tasks
These are live execution units tracked in app state.
Examples include:
- local shell jobs
- local agents
- remote agents
- in-process teammates
- workflows
- monitor jobs
- dream/background maintenance tasks

These have stable runtime statuses:
- `pending`
- `running`
- `completed`
- `failed`
- `killed`

They support lifecycle control such as stop/kill and output retrieval.

### 2.2 Persistent shared task-list items
These are durable coordination records used by teams/swarms.
They represent shared units of work and include fields like:
- `id`
- `subject`
- `description`
- `activeForm`
- `owner`
- `status`
- `blocks`
- `blockedBy`
- `metadata`

These use a different status set:
- `pending`
- `in_progress`
- `completed`

### Preservation requirement
Do not collapse these into one generic abstraction.
A compatible rewrite must preserve:
- live runtime tasks for process/job control
- durable shared tasks for coordination and planning

---

## 3. Runtime task contract

## 3.1 Runtime task types
The verified runtime task kinds are:

```ts
'local_bash'
'local_agent'
'remote_agent'
'in_process_teammate'
'local_workflow'
'monitor_mcp'
'dream'
```

### Preservation requirement
A rewrite may internally rename implementations, but it must preserve a typed runtime-task model with at least equivalent distinctions between shell jobs, delegated agents, in-process teammates, and remote/background services.

---

## 3.2 Runtime task lifecycle
Each tracked runtime task has:
- an ID
- a type
- a status
- a description
- start/end timing
- persisted output location and offset
- notification state

Terminal statuses are:
- `completed`
- `failed`
- `killed`

### Preservation requirement
A rewrite must preserve:
- terminal-vs-live status distinction
- task lookup by ID
- output association per task
- app-state visibility of currently tracked tasks

---

## 3.3 Runtime task control semantics
The task control layer must preserve:
- registry-based task implementations
- stop/kill by task ID
- validation against the live task registry rather than only durable history
- stable output retrieval through task-oriented interfaces

This is the behavioral basis for tools like task stop/get/list and for UI/task panes.

---

## 4. Persistent shared task-list contract

## 4.1 Purpose
The persistent task list is the shared coordination plane for swarm/team work.

Its purpose is to support:
- discoverable work items
- ownership claiming
- status tracking
- dependency graphs
- teammate assignment visibility
- durable coordination across concurrent actors

### Preservation requirement
A rewrite must preserve a shared durable coordination surface, even if file-backed storage is replaced by another durable backend.

---

## 4.2 Required shared task semantics
The following semantics are compatibility-relevant:
- stable task-list identity per team/session context
- monotonic task IDs within a logical task list
- no ID reuse in a live logical task list
- atomic create/claim/update behavior
- durable ownership state
- durable dependency edges
- list/get/update/delete operations
- teammate status derivation and teammate unassignment support

### Preservation requirement
Concurrency safety is mandatory. File locks are one implementation, not the contract; atomicity is the contract.

---

## 4.3 Dependency semantics
The dependency model has directional meaning that must remain stable:
- `addBlocks`: this task blocks those tasks
- `addBlockedBy`: those tasks block this task

Summary views may suppress blockers that are already completed, but storage still retains historical blocker relationships.

### Preservation requirement
Do not invert these edge directions in a rewrite.

---

## 4.4 Ownership and claiming semantics
The task system supports explicit ownership and atomic claiming.
A rewrite must preserve:
- owner field as part of shared task state
- atomic claim checks so two agents do not both acquire the same task silently
- auto-assignment behavior where documented by the task-update flow
- teammate-assignment visibility and routing support

---

## 5. Team/swarm lifecycle

## 5.1 Team creation
Team creation is more than making a name.
A compatible rewrite must preserve the coupling between:
- creating a team identity
- persisting team metadata
- computing/assigning a deterministic lead agent identity
- initializing a team-scoped task-list namespace
- switching task routing into that team context
- registering the team for cleanup on session exit
- materializing team context into app state

### Important consequence
Once a team is active, task APIs operate in the team task-list namespace rather than the default per-session namespace.

---

## 5.2 Team deletion
Team deletion must preserve guarded cleanup semantics.

Required behavior:
- inspect the current team state
- refuse deletion if any non-lead teammate is still active
- allow inactive members marked not active to stop blocking deletion
- clean up persisted team state/directories
- unregister cleanup hooks
- clear leader team identity and related app-state context

### Preservation requirement
Deletion blocked by active non-lead teammates is part of the external coordination model and must remain.

---

## 5.3 Leader vs teammate roles
A compatible rewrite should preserve a role distinction between:
- leader / team lead
- teammates / delegated workers

This distinction matters for:
- approval and response routing
- shutdown-response targeting
- visibility and ownership behavior
- task-list routing and team management privileges

---

## 6. Messaging and mailbox semantics

## 6.1 Coordination is message-oriented
Swarm coordination is not just shared mutable state.
It includes explicit message passing across workers/backends.

A compatible rewrite must preserve message-oriented coordination for:
- teammate-to-teammate messages
- leader/teammate control messages
- bridge/socket forwarding where supported
- mailbox-style direct delivery

---

## 6.2 Supported addressing model
The `to` field supports these routing families:
- bare teammate name
- broadcast `*`
- `bridge:<destination>`
- `uds:<destination>`
- validated local agent ID where supported

### Preservation requirement
Preserve bare-name routing and reject `@name` syntax at the user-facing contract layer.

---

## 6.3 Plain-text message semantics
Plain-text sends generally require:
- a non-empty destination
- a message string
- a summary field, except for some UDS-specific cases

Broadcast is valid only for plain text.
Mailbox-style and bridge routes are distinct delivery paths and must remain distinguishable.

---

## 6.4 Structured control-message protocol
The structured coordination protocol includes these message kinds:

```ts
{ type: 'shutdown_request'; reason?: string }

{
  type: 'shutdown_response'
  request_id: string
  approve: boolean
  reason?: string
}

{
  type: 'plan_approval_response'
  request_id: string
  approve: boolean
  feedback?: string
}
```

### Preservation requirement
A compatible rewrite must preserve this control-message union or a compatibility wrapper that accepts and emits an equivalent protocol.

---

## 6.5 Routing constraints for control messages
Structured messages must preserve these restrictions:
- not broadcastable to `*`
- not sendable to `bridge:` or `uds:` destinations
- `shutdown_response` must target `team-lead`
- if a shutdown response denies approval, a reason is required

These are protocol-level validation rules, not incidental implementation details.

---

## 6.6 Auto-resume on local delivery
If a targeted local agent is stopped but resumable, incoming-message delivery attempts transcript-based auto-resume before final delivery.

### Preservation requirement
A rewrite should preserve stopped-local-agent auto-resume behavior for incoming local message delivery.

---

## 7. Approval and shutdown coordination

## 7.1 Shutdown request flow
The system supports explicit shutdown-request messaging.
This allows graceful coordinated worker termination rather than treating every stop as an immediate kill.

### Preservation requirement
A rewrite must preserve the distinction between:
- graceful terminate / shutdown request
- hard kill / immediate abort

---

## 7.2 Shutdown response flow
Shutdown approvals and denials are explicit messages.
When approved:
- in-process controllers may hard-abort immediately
- non-in-process execution can fall back to graceful shutdown paths

When denied:
- the response includes an explicit negative decision
- a reason is required

### Preservation requirement
A rewrite must preserve explicit approval/denial signaling rather than reducing shutdown handling to a single opaque boolean or local callback.

---

## 7.3 Plan approval response flow
Plan-approval responses are a distinct structured control path.
They are not equivalent to generic text messages and should retain separate handling semantics.

---

## 8. Teammate execution backend model

## 8.1 Common backend-neutral executor surface
A compatible rewrite must preserve a backend-neutral teammate executor contract with operations equivalent to:
- `spawn`
- `sendMessage`
- `terminate`
- `kill`
- `isActive`

This is the core abstraction that lets orchestration stay independent of execution medium.

---

## 8.2 Spawn configuration requirements
Teammate spawn config includes all of the following semantic inputs:
- name
- team name
- optional color
- whether plan mode is required
- prompt
- cwd
- optional model override
- optional system prompt and prompt mode
- optional worktree path
- parent session ID
- permission settings
- whether permission prompts are allowed

### Preservation requirement
A rewrite must preserve the ability to launch teammates with explicit identity, prompt, working directory, model/system-prompt policy, parent-session linkage, and permission context.

---

## 8.3 Spawn result requirements
Spawn results must expose at least:
- success/failure
- stable agent identity
- optional backend-specific control handles such as pane ID, abort controller, or task ID

### Preservation requirement
Backend-specific handles may differ internally, but the common success/agent-ID contract must remain stable.

---

## 9. Backend differences that matter

## 9.1 In-process execution
In-process teammates:
- run in the same process
- are logically isolated from the leader’s turn-local message state
- communicate through mailbox/message mechanisms rather than shared-object mutation
- are tracked as app-state-visible tasks
- use abort-controller-based lifecycle control
- distinguish graceful terminate from hard kill

### Preservation requirement
A rewrite must preserve same-process logical isolation. “Same process” must not imply unrestricted mutation of the leader conversation state.

---

## 9.2 Pane-backed execution
Pane backends such as tmux/iTerm-style backends encapsulate:
- pane creation
- sending commands to panes
- visual metadata like titles/colors/status
- show/hide/rebalance operations
- pane kill/hide/show lifecycle

### Preservation requirement
A rewrite does not need tmux forever, but it must preserve the adapter boundary between orchestration logic and terminal-pane control.

---

## 9.3 Remote or non-local execution
The architecture also supports remote-style or out-of-process workers.
At the coordination level, the important thing is that these still fit behind the same executor lifecycle shape and remain compatible with shared messaging and task visibility.

---

## 10. Relationship between todos and swarm tasks

The product uses both:
- a local todo/checklist mechanism for the current agent
- a durable shared task list for swarm coordination

### Preservation requirement
Do not substitute one for the other.
A rewrite should preserve:
- local todo state as lightweight working memory / execution discipline
- shared task list as durable multi-agent coordination state

This separation is intentional and operationally useful.

---

## 11. Implementation guidance for a clean-room rewrite

A compatible rewrite should implement the coordination layer in roughly this order:

1. build the durable shared task-list model with atomic claiming and dependency edges
2. build team lifecycle creation/deletion around that namespace
3. implement a backend-neutral teammate executor interface
4. implement in-process execution first, preserving logical isolation
5. add pane-backed or remote-style backends behind the same interface
6. add explicit structured message routing for shutdown and approvals
7. keep local todo/checklist support separate from swarm tasks

This ordering captures the highest-value behavior without requiring the exact original file layout.

---

## 12. Critical invariants to preserve

A rewrite is at high risk of behavior regressions if it loses any of these:

- distinction between runtime tasks and durable shared tasks
- monotonic, non-reused shared task IDs within a live logical task list
- atomic claim/update semantics
- stable dependency-edge direction
- team creation coupling to team-scoped task routing
- team deletion blocked by active non-lead teammates
- backend-neutral spawn/send/terminate/kill/isActive contract
- graceful terminate vs hard kill distinction
- same-process logical isolation for in-process teammates
- explicit structured shutdown/approval message protocol
- stopped-local-agent auto-resume on message delivery
- separation of local todo state from shared team coordination state

---

## 13. Notes on wording and clean-room safety

This document intentionally describes semantics rather than requiring exact user-visible strings.
Unless a companion doc explicitly marks text as compatibility-critical protocol text, message wording here should be treated as illustrative rather than normative.

---

## 14. Confidence and limits

High confidence:
- the orchestration semantics consolidated here are directly supported by the verified companion docs listed above
- the lifecycle, task-type, backend, and message-protocol distinctions are all explicitly documented elsewhere in this repo

Limit:
- this document is a consolidation layer, not a fresh source-code inspection pass
- if deeper backend internals are later inspected, they may warrant an additional implementation appendix
