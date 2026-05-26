# Feature prioritization for a clean-room rewrite

This document helps implementation teams avoid overbuilding around the most detailed docs first.

It classifies the documented system into:
- MVP / must-have for a credible rewrite
- compatibility-critical but phaseable
- optional or later-stage capabilities

It is intentionally product-planning guidance, not a source-equivalence spec.

Companion docs:
- `docs/hld.md`
- `docs/interfaces-and-endpoints.md`
- `docs/tool-contracts.md`
- `docs/task-and-swarm.md`
- `docs/implementation-notes-and-gotchas.md`

---

## 1. How to use this document

Use this document when deciding:
- what to implement first
- what can be stubbed or deferred
- which documented details are core to correctness and safety
- which documented details matter mainly for advanced coordination or premium integrations

The categories below are practical planning buckets, not statements that later-tier items are unimportant.
They only mean a team can sequence the work without breaking the core rewrite strategy.

---

## 2. Tier definitions

## 2.1 Tier 0: safety and runtime kernel
These are the things the rewrite cannot credibly ship without.
If these are wrong, the product is either unsafe or fundamentally incompatible.

## 2.2 Tier 1: MVP product surface
These features are required for a useful day-to-day coding assistant experience.
A rewrite without them may be technically interesting but not operationally competitive.

## 2.3 Tier 2: compatibility-critical expansion
These features are important to preserve medium-term compatibility, advanced workflows, and production parity, but can be staged after the kernel and MVP are stable.

## 2.4 Tier 3: advanced or optional capabilities
These are valuable, but they should not block initial implementation unless they are central to the target product strategy.

---

## 3. Tier 0: safety and runtime kernel

Implement first, before broad feature expansion.

### 3.1 Streaming conversation kernel
Must preserve:
- one stateful engine per conversation/session
- async streaming turn execution
- in-turn tool loop execution
- same-turn retry/fallback behavior
- cancellation handling
- transcript repair semantics such as tombstones or equivalent

### 3.2 Persistence/resume essentials
Must preserve:
- early-enough persistence of user input for resumability
- distinction between streamed UI events and durable transcript writes
- replay/resume correctness boundaries
- compaction/snipping structure or an equivalent projection model

### 3.3 Permission and path safety
Must preserve:
- explicit permission modes and allow/deny/ask behavior
- dangerous path handling
- UNC/network-path prevalidation before probing on Windows-like platforms
- built-in protection for configuration-sensitive paths

### 3.4 File mutation safety
Must preserve:
- read-before-write enforcement
- partial-read vs full-read distinction
- stale-read checks
- notebook-specific mutation path

### 3.5 Shell safety model
Must preserve:
- per-command sandbox routing
- policy-controlled unsandboxed override
- read-only classification with argument sensitivity
- deny-over-allow semantics
- git/hook/bare-repo hardening
- background task identity and control semantics

---

## 4. Tier 1: MVP product surface

These are the minimum feature surfaces needed for a capable implementation-oriented agent.

## 4.1 Core tools
Implement early:
- `Read`
- `Edit`
- `FileWrite`
- `Glob`
- `Grep`
- `Bash`
- `PowerShell` where Windows support matters
- `NotebookEdit` if notebook workflows matter for target users
- `LSP`

These are the daily-driver tools and should be treated as the core tool catalog.

## 4.2 Core model and prompt routing
Implement early:
- base model selection
- runtime effective model selection
- fallback model support
- plan-mode-sensitive routing where applicable
- prompt/context layering at least to the degree required for stable behavior

## 4.3 Basic task control
Implement early:
- runtime background task tracking
- task stop/kill behavior
- output retrieval for background shell/agent work

This is needed for long-running shell tasks and delegated work.

---

## 5. Tier 2: compatibility-critical expansion

These are important for product parity and sophisticated workflows, but can follow once Tier 0 and Tier 1 are stable.

## 5.1 Shared durable task coordination
Implement after MVP kernel/tools if needed:
- persistent shared task-list storage
- ownership/claiming
- blocker graph semantics
- task create/list/get/update flows
- concurrency-safe shared mutation

## 5.2 Team/swarm orchestration
Implement after the single-agent product is stable:
- team lifecycle
- teammate execution backends
- mailbox/message routing
- approval/shutdown protocols
- local auto-resume on directed message delivery

## 5.3 Skill and slash-command system
Implement after the main tool surface:
- slash-command invocation
- inline vs forked skill semantics
- context-modifying inline commands
- delegated/forked skill execution

## 5.4 MCP integrations
Implement after the core built-in tool system is solid:
- MCP tool participation in unified tool pool
- resource listing/reading
- server authentication flows
- dynamic MCP discovery and late binding

## 5.5 Remote APIs and remote session flows
Implement after local product viability unless remote is central to launch:
- sessions API
- environments API
- remote trigger API
- bridge/session lifecycle logic

---

## 6. Tier 3: advanced or optional capabilities

These should not usually block initial delivery.

Examples:
- advanced multi-backend pane orchestration
- premium or enterprise-specific remote environment workflows
- cron/Kairos scheduling features
- aggressive prompt-compaction tuning beyond correctness
- extra UX refinements around picker labels, reminders, and telemetry
- niche compatibility workarounds that are helpful but not launch-blocking

Note: some “optional” items may still be required if they are part of the intended product differentiation. This tiering is generic, not business-specific.

---

## 7. What not to overbuild early

Implementation teams should explicitly avoid starting with:
- the most elaborate swarm flows
- all remote integrations
- every compatibility nudge and heuristic
- every UI-facing wording nuance
- rare provider-specific model-picker refinements

Those are valuable later, but they are not the fastest route to a safe, useful rewrite.

The right order is usually:
1. safe kernel
2. core file/shell/search tools
3. persistence/resume correctness
4. model routing and fallback
5. background task control
6. shared coordination and advanced orchestration
7. premium/remote/optional surfaces

---

## 8. Delivery checkpoints

A practical staged plan is:

### Checkpoint A: safe single-agent prototype
Required:
- streaming turn loop
- transcript persistence basics
- `Read` / `Edit` / `Write` / `Glob` / `Grep`
- shell execution with safety model
- permission engine basics

### Checkpoint B: daily-driver coding assistant
Required:
- `LSP`
- background task management
- model routing/fallback parity
- notebook support if target users need it
- robust recovery/compaction semantics

### Checkpoint C: coordinated/advanced workflows
Required:
- durable shared task list
- team lifecycle
- delegated agents
- mailbox/control messaging
- skill system

### Checkpoint D: ecosystem and premium parity
Required:
- MCP resource/auth flows
- remote sessions/environments/triggers
- cron/scheduled work
- extra provider/picker/entitlement nuance

---

## 9. Bottom line

If resources are limited, optimize for this order:
- correctness and safety first
- core coding tools second
- persistence and model-routing parity third
- orchestration and ecosystem breadth after that

That sequencing best matches the actual risk profile in the current documentation: the biggest implementation failures would come from unsafe kernel/tool behavior, while the biggest completeness gaps were around coordination and some peripheral tool families.
