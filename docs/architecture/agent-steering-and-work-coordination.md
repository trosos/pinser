# Agent steering and work coordination for a clean-room rewrite

This document captures two runtime design areas that are easy to underrate during a clean-room rewrite because they are not hard external APIs, but they do encode useful operational lessons from the implementation:

- the distinction between a lightweight per-agent todo list and a durable shared task list
- the use of nudges and soft steering signals to keep agent behavior on track without turning every deviation into a hard error

This is intentionally a pragmatic design/compatibility note, not a bit-for-bit reproduction spec.

Companion docs:
- `docs/task-and-swarm.md`
- `docs/implementation-notes-and-gotchas.md`
- `docs/turn-failure-and-retry-state-machine.md`
- `docs/model-and-request-shaping.md`
- `docs/transcript-and-persistence-semantics.md`

Primary inspected sources for this pass:
- `src/tools/TodoWriteTool/TodoWriteTool.ts`
- `src/tools/TodoWriteTool/prompt.ts`
- `src/tools/TaskCreateTool/TaskCreateTool.ts`
- `src/tools/TaskListTool/prompt.ts`
- `src/tools/TaskGetTool/prompt.ts`
- `src/tools/TaskUpdateTool/TaskUpdateTool.ts`
- `src/utils/tasks.ts`
- `src/query/tokenBudget.ts`
- `src/utils/tokenBudget.ts`

---

## 1. Why this matters

These mechanisms are not the core model API contract, but they are still worth documenting because they capture places where the implementation uses lightweight structure and steering to reduce agent drift and coordination mistakes.

A rewrite team could otherwise waste time by:
- conflating the per-agent todo list with the shared multi-agent task list
- treating every steering behavior as either a strict hard error or as disposable prompt flavor
- rediscovering, through trial and error, that some situations are better handled by soft continuation/reminder messages than by restarting the turn loop or rejecting the action

### Rewrite stance
Preserve the design intent and behavioral role of these mechanisms, but not necessarily every exact string, threshold, or feature-flag gate.

---

## 2. Two different coordination layers exist

The implementation uses two distinct coordination mechanisms:

1. **Session/agent todo list**
   - lightweight working checklist
   - oriented around the currently active agent
   - optimized for progress tracking during a turn/session

2. **Shared durable task list**
   - multi-agent coordination/work-queue mechanism
   - oriented around task claiming, ownership, dependencies, and shared visibility
   - optimized for swarms/teams rather than a single agent’s scratchpad

### Rewrite requirement
A rewrite should preserve the distinction between these two layers even if the concrete storage or tool names change.

---

## 3. Todo list semantics

## 3.1 Purpose
The todo list is a lightweight execution checklist used to track what the current agent intends to do or is doing.

It is not the same thing as the durable task list used for swarm coordination.

### Design intent
The todo list exists to improve local execution discipline and user-visible progress tracking, not to serve as the system of record for multi-agent scheduling.

---

## 3.2 Update model
The todo tool updates the current todo list as a whole list replacement rather than as a sequence of append/remove patch operations.

### Rewrite recommendation
It is useful to preserve whole-list replacement semantics because they keep the model’s coordination problem simple: at each update, it publishes the current intended checklist state rather than having to compute incremental patches correctly.

Equivalent designs are acceptable as long as the rewrite preserves the same ergonomic benefit.

---

## 3.3 Scope and identity
The implementation keys todo state to the current agent when running in an agent context, otherwise to the session.

That means the todo list is effectively:
- per-agent inside agent/subagent execution
- per-session for the main agent/session flow

### Rewrite requirement
Preserve the fact that todos are local working state, not a global swarm work queue.

---

## 3.4 Completion normalization
When all todo items are marked completed, the stored list is normalized to an empty list rather than retaining a completed checklist forever.

### Rewrite recommendation
Preserve this or an equivalent “clear completed local checklist” behavior. It reduces stale checklist clutter and keeps the todo list focused on active work.

---

## 3.5 Role in agent discipline
The tool result explicitly reminds the agent to continue using the todo list after modification.

### Design intent
This is a soft behavioral reinforcement pattern: the system does not merely mutate state; it also reminds the model that checklist maintenance is part of the expected workflow.

### Rewrite recommendation
The exact wording is not important, but preserving some form of lightweight reinforcement is likely beneficial.

---

## 4. Durable task-list semantics

## 4.1 Purpose
The task list is a durable shared coordination plane for work distribution, especially in multi-agent or swarm-style execution.

Unlike the todo list, the task list is meant to support:
- discoverability of available work
- task claiming and ownership
- dependency tracking
- team-wide visibility
- continued coordination across concurrent actors

---

## 4.2 Task data model role
The task system carries richer coordination state than todos, including concepts such as:
- task identity
- subject/description
- status
- owner
- dependency relationships (`blocks`, `blockedBy`)
- optional metadata

### Rewrite requirement
Preserve the existence of a richer durable coordination object for shared work, even if the precise schema evolves.

---

## 4.3 Shared identity resolution matters
The implementation resolves the active task-list identity from several possible contexts so that leaders, process-based teammates, and in-process teammates can all converge on the same shared task list.

### Rewrite requirement
Preserve the principle that swarm participants must resolve to a common coordination namespace rather than silently creating separate local task lists.

The exact precedence rules do not have to match if the architecture changes, but the shared-identity requirement is important.

---

## 4.4 Concurrency protection is intentional
The implementation uses file-backed locking/high-watermark coordination so multiple agents can mutate the task list without corrupting IDs or clobbering each other.

### Rewrite requirement
If the rewrite keeps a shared mutable task list, it must preserve safe concurrent mutation semantics.

This does not require file locks specifically, but it does require:
- monotonic task identity assignment
- atomic enough mutation semantics for concurrent actors
- avoidance of duplicate ID allocation or silent overwrite races

---

## 4.5 Swarm workflow implications
Task-list prompts and helpers encode a clear intended workflow:
- discover available work
- prefer unblocked/unowned tasks
- claim work explicitly
- update ownership and status as work progresses
- use dependency state to determine what can proceed next

### Rewrite recommendation
Preserve these workflow assumptions at the product level, even if the tool surface changes.

---

## 5. Relationship between todo list and task list

The simplest way to think about the two systems is:

- **Todo list** = what *this agent* is currently tracking as its own immediate checklist
- **Task list** = what *the team/system* is tracking as shared units of coordinated work

A compatible rewrite should avoid collapsing both into a single abstraction unless it is very deliberate about preserving both use cases.

### Why that separation helps
It lets the product have:
- a cheap, low-friction checklist for local execution discipline
- a heavier, durable coordination structure for shared planning and work allocation

That split is useful and likely worth preserving.

---

## 6. Nudges and soft steering as a design pattern

## 6.1 The system uses soft steering, not only hard enforcement
The implementation does not rely only on hard state transitions such as “reject,” “retry,” or “fail.” It also uses lightweight steering messages to shape agent behavior.

Representative forms include:
- continuation nudges when token budget logic decides the agent should keep working
- reminders embedded in tool results
- verification-oriented nudges when a work checklist is closed out without an obvious verification step

### Rewrite requirement
Preserve the general pattern that some model-control problems are better handled by soft steering than by strict rejection.

---

## 6.2 Not all nudges belong at the same layer
The implementation uses nudges in more than one way:
- some are injected into turn flow as continuation messages
- some are appended to tool results
- some operate as workflow reminders tied to a specific state transition

### Rewrite recommendation
Preserve the idea that steering should be attached to the layer where the issue arises:
- turn-loop continuation problems belong in the turn engine
- checklist hygiene reminders can live on todo tool results
- coordination reminders can live near task/todo transitions

---

## 6.3 Nudges are usually better treated as policy, not protocol
In most cases, the exact wording of a nudge is not the compatibility surface.

What matters is:
- when the nudge is triggered
- what behavior it is trying to encourage or suppress
- whether it is advisory or effectively mandatory in practice

### Rewrite requirement
Document nudge triggers and design intent, but do not overfit the rewrite to exact message text unless a downstream integration depends on it.

---

## 7. Token-budget continuation nudges

## 7.1 User-requested token budgets exist
The implementation can parse token-budget directives from user text, including shorthand and verbose forms.

The parsed budget is then used by turn-loop logic to decide whether to continue working rather than stopping/summarizing too early.

### Rewrite requirement
If the rewrite keeps token-budget-aware execution, preserve the distinction between:
- an explicit user-requested work budget
- ordinary turn completion logic

---

## 7.2 Continuation is proactive, not purely reactive
The token-budget tracker does not merely stop when the budget is exhausted. It can proactively continue the turn while the work is still significantly below the target budget.

### Design intent
This exists because otherwise the agent may summarize or stop too early relative to the requested work budget.

---

## 7.3 Diminishing-returns logic exists to prevent endless continuation
The implementation tracks repeated continuations and recent token deltas so it can stop nudging when additional continuation appears unproductive.

### Rewrite requirement
If the rewrite keeps budget-based continuation, it should also preserve a diminishing-returns brake. Otherwise the product risks inefficient endless “keep going” loops.

---

## 7.4 Continuation is conveyed as a steering message
The continuation decision yields a synthetic message whose purpose is effectively:
- you have not yet used enough of the requested work budget
- keep working
- do not summarize yet

### Rewrite recommendation
Preserve the semantic behavior, not the exact text.

---

## 8. Verification nudges on todo closeout

## 8.1 A structural closeout nudge exists
When the main-thread agent closes out a sufficiently large todo list and no item appears to represent verification work, the tool can append a verification-oriented reminder.

### Design intent
This is a guard against a common failure mode:
- the agent executes several implementation steps
- closes the checklist
- moves directly to final summary
- verification is skipped or reduced to self-asserted caveats

The nudge is meant to push the workflow toward explicit verification before finalization.

---

## 8.2 This is a workflow heuristic, not a hard invariant
The implementation gates this behavior behind contextual conditions and feature flags.

### Rewrite recommendation
Preserve the idea that significant work completion may warrant a verification reminder, but do not treat the exact heuristic as a strict compatibility requirement unless the rewrite wants similar product behavior.

---

## 8.3 Tool-result placement is meaningful
This nudge is attached to the todo tool result rather than being emitted as an unrelated system-level event.

### Design insight
That placement ties the reminder to the exact state transition that caused it: checklist closure.

A rewrite does not need to use the same placement, but it should preserve locality between trigger and steering signal where practical.

---

## 9. What is essential vs optional to preserve

## Essential
A rewrite should preserve:
- the distinction between local todo tracking and shared durable task coordination
- the existence of a richer coordination object for swarm/shared work
- safe concurrent mutation semantics for shared tasks
- the design pattern of using soft steering in places where hard failure would be counterproductive
- some continuation strategy if the product supports user-requested token budgets

## Useful but optional to preserve exactly
A rewrite may change:
- exact tool names
- exact prompt/tool-result wording
- exact budget thresholds
- exact closeout heuristic for verification reminders
- exact storage backend for task coordination
- exact todo storage representation

---

## 10. Practical rewrite guidance

If implementing from these docs, a sensible order is:

1. implement the durable task-list coordination model first
2. implement a simple local todo/checklist mechanism separately
3. add minimal reminder behavior to keep todo usage sticky
4. add budget-based continuation only if the product still exposes explicit work-budget semantics
5. add verification nudges only if testing shows the same closeout failure mode in practice

This preserves the highest-value lessons without forcing unnecessary bit-for-bit reproduction.

---

## 11. Bottom line

These mechanisms are not the center of the compatibility surface, but they are worth documenting because they encode practical lessons about:
- how to separate local execution discipline from shared coordination
- how to steer model behavior without overusing hard errors
- how to avoid common completion/verification drift in long-running agentic work

For a clean-room rewrite, the important thing is to preserve the intent and role of these mechanisms, not necessarily their exact implementation details.
