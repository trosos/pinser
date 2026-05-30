# Phase 3 scope and kickoff note

This document defines the implementation kickoff scope for Phase 3: transcript persistence, resume, and recovery basics.

For canonical project phase status, see [`docs/project-roadmap.md`](../project-roadmap.md).

It complements, and does not replace:

- [`docs/project-roadmap.md`](../project-roadmap.md)
- [`docs/architecture/hld.md`](../architecture/hld.md)
- [`docs/architecture/transcript-and-persistence-semantics.md`](../architecture/transcript-and-persistence-semantics.md)
- [`docs/architecture/session-compaction-and-recovery.md`](../architecture/session-compaction-and-recovery.md)
- [`docs/architecture/INDEX.md`](../architecture/INDEX.md)
- [`docs/phase2.1/scope.md`](../phase2.1/scope.md)

The architecture documents remain the normative compatibility references. This file exists to turn the roadmap’s Phase 3 goal into a small, implementation-oriented starting point so contributors can begin the persistence layer without repeatedly re-deciding what belongs in this phase.

## Purpose

Phase 2 and Phase 2.1 established a safer local in-memory runtime with bounded tool behavior and a tighter local tool surface.

Phase 3 should now make that runtime durable enough to survive interruption and support credible session continuation.

This phase is the point where Pinser stops being only an in-memory local assistant and starts becoming a resumable session runtime.

The main discipline for this phase is:

- preserve the current streaming turn/runtime model
- add persistence as a distinct layer rather than smearing file writes through the turn loop
- make recovery explicit and testable
- keep the initial durability slice narrower than later compaction and robustness phases

## Position relative to the roadmap

The roadmap already marks Phase 3 as the next planned implementation focus after Phase 2.1.

Phase 3 owns the first persistence and recovery baseline, not the entire long-session maintenance story.

Rule of thumb:

- **Phase 3** owns durable transcript/session structure, prompt-history separation, resume loading, and basic interruption recovery.
- **Phase 4** owns broader runtime robustness such as model routing, retries, and broader runtime/transcript-scale result shaping.
- **Phase 5** owns compaction and deeper long-session recovery hardening.

That means Phase 3 should land the smallest persistence model that is structurally correct and extensible, without prematurely implementing the full compaction and recovery surface described in the architecture documents.

## Architecture takeaways shaping this phase

The high-level and persistence architecture docs imply several constraints that should shape implementation from the start.

### 1. Persistence is a separate runtime concern

The high-level architecture distinguishes:

- session-local in-memory conversation state
- turn-local working state
- persisted transcript/session state
- prompt history as a separate persistence surface

Phase 3 should preserve those distinctions.

In particular:

- transcript persistence should not be treated as the same store as prompt history
- recovery logic should not be embedded ad hoc into CLI code paths
- turn execution should remain the runtime kernel, with persistence attached at explicit boundaries

### 2. The transcript is more than chat messages

The persistence architecture is clear that the durable record is a mixed-entry log, not only a sequence of user and assistant chat messages.

Even if the first implementation slice stays modest, it should leave room for:

- transcript messages
- session metadata entries
- repair/recovery markers or equivalent later extension points

A Phase 3 implementation should therefore avoid designing storage as “just save a list of messages to JSON”.

### 3. Resume is a normalization-and-repair pipeline

The architecture documents do not describe resume as raw deserialization.
They describe it as:

- loading persisted entries
- reconstructing effective conversation state
- filtering invalid or incomplete artifacts
- detecting interruption state
- preparing a stable resumed conversation

Phase 3 does not need every advanced recovery path yet, but it should establish this shape from the beginning.

### 4. Lazy, append-oriented persistence matters

The architecture documents emphasize append-only transcript semantics and lazy session-file materialization.

Phase 3 should therefore prefer:

- per-session append-oriented transcript storage
- explicit flush points
- session creation on first meaningful conversation activity rather than unconditional eager file creation

### 5. Tool-output hardening from Phase 2.1 is not the final persistence model

Phase 2.1 added bounded, prompt-facing framing of tool output as untrusted data.

Phase 3 should preserve that safety posture while beginning the structural split between:

- tool-result records as persisted data
- prompt-facing normalized content
- replay/recovery inputs

This phase should begin that separation, even if richer offloading and aggregate budgeting continue later.

## Phase 3 minimum required implementation

Phase 3 minimum scope is the smallest implementation that should count as a credible persistence/resume baseline.

### Required persistence capabilities

Implement at minimum:

- persistent per-session transcript storage
- session identity and storage location handling
- early persistence of committed user input sufficient for resume correctness
- transcript loading for an existing session
- a basic resume path that reconstructs a usable conversation from persisted records
- a prompt-history store kept separate from transcript persistence

### Required behavioral guarantees

The minimum implementation should preserve these behavior classes:

- append-oriented transcript writes with deterministic ordering per session
- no silent loss of committed user input across interruption and resume
- resume from persisted session state without treating the transcript as a raw in-memory object dump
- explicit distinction between durable transcript state and ephemeral progress/runtime-only events
- clear handling of interrupted or partial turn artifacts through a defined recovery path

### Required recovery behavior

Implement at minimum:

- reconstruction of persisted conversation state for one session
- detection of at least the basic interrupted-session cases needed for resume
- a defined strategy for partial assistant output or incomplete turn artifacts
- transcript validation/sanitization for obviously invalid persisted records

This does not need to include full compaction-aware recovery yet.
It does need to prevent Phase 3 persistence from becoming a naive replay mechanism that later phases must replace entirely.

### Required testing

Phase 3 should include tests for at least:

- persisting and reloading a simple session
- interruption after user input has been committed
- interruption during or after partial assistant/tool activity where supported by the current runtime
- separation of prompt history from transcript storage
- basic resume behavior using a real persisted session fixture or equivalent end-to-end test path

## Phase 3 implementation-shaping decisions

The following decisions should guide contributors during the kickoff of this phase.

### 1. Start with a small but real transcript format

The first transcript format should be durable and append-oriented, even if it does not immediately implement the full richness of later phases.

That means:

- prefer a session-scoped append log
- include enough structure to distinguish message entries from session metadata
- avoid one-shot snapshot rewrites as the main persistence strategy

### 2. Preserve a dedicated recovery loader

Do not make callers reconstruct session state manually from stored files.

Instead, introduce a dedicated load/recover path that owns:

- reading persisted records
- validating or sanitizing them
- rebuilding the effective conversation state for resume

This keeps later compaction and repair work evolvable.

### 3. Keep progress and transport noise out of durable semantics

The architecture docs are explicit that progress-style events are not the durable conversation chain.

Phase 3 should preserve this even if the current runtime emits a richer set of runtime events internally.

### 4. Make session adoption and resume explicit

Resuming an existing session should be modeled as adopting existing persisted state, not creating a new session and copying messages around informally.

Even if the initial implementation is simple, the state transition should be explicit enough to extend later.

### 5. Do not pull compaction into this phase by accident

The compaction and long-session reconstruction documents are important reading for future-safe design, but Phase 3 should not expand into full compaction implementation.

Instead, use them to avoid dead ends:

- choose append-oriented persistence
- leave room for later metadata and boundary records
- design recovery as a loader pipeline

## Explicitly in scope now

The following work should be considered active Phase 3 scope.

### 1. Transcript persistence baseline

Implement:

- per-session transcript storage under a stable project/session location
- append-oriented recording of durable conversation entries
- session-file materialization only when a session has meaningful persisted content
- explicit flush behavior at cleanup or other durability boundaries

### 2. Prompt-history separation

Implement:

- a prompt-history mechanism or store that is separate from transcript persistence
- tests proving transcript persistence and prompt-history behavior are not the same concern

### 3. Resume loading and basic recovery

Implement:

- loading a persisted transcript for a session
- reconstruction of the effective conversation state from persisted records
- detection of interrupted-session cases needed for basic continuation
- a minimal repair/tombstone or equivalent strategy for partial/incomplete persisted turn artifacts

### 4. Persistence-aware runtime integration

Implement:

- explicit persistence boundaries in the session/turn runtime
- persistence of user input early enough for interruption-safe resume
- integration tests proving the runtime can continue from persisted state rather than only from in-memory state

### 5. Documentation and contributor guidance

Add or update local phase documentation as implementation clarifies:

- transcript file shape and persistence boundaries
- which runtime events are durable vs ephemeral
- what resume guarantees Phase 3 does and does not make

## Explicitly out of scope for Phase 3

Phase 3 should stay focused on basic durability and recovery. The following work is important but should not be required to call this phase complete.

### Deferred primarily to Phase 4

- configurable model routing and fallback behavior
- broader retry-state machinery and daily-driver failure handling
- broader runtime- and transcript-scale result-budgeting beyond the minimum persistence-safe structure needed here
- PowerShell and approval-mode breadth deferred from earlier phases

### Deferred primarily to Phase 5

- full compaction/checkpointing implementation
- compaction-aware long-session maintenance workflows
- deeper replay/poisoning and reconstruction hardening tied to compaction boundaries
- richer recovery optimization for very large transcripts

### Deferred primarily to Phase 6 and later

- background task durability and lifecycle
- worker/agent sidechain persistence beyond whatever minimal structure is needed not to block future work
- team/shared-task coordination persistence
- remote/bridge-backed session hydration

## Ordered execution plan

The work should land in the following order.

### 1. Define the persistence boundary and transcript shape

Land first:

- the session persistence interface
- the initial durable transcript entry schema
- the distinction between durable transcript entries and prompt history
- a small local implementation note if needed

Why first:

- it fixes the core storage boundary before runtime call sites spread
- it makes later resume tests and integration work concrete

### 2. Persist committed user input and simple assistant turns

Land second:

- persistence for basic user and assistant conversation records
- session materialization on first meaningful content
- deterministic append behavior and flush handling

Why second:

- this creates the minimum real durability path
- it allows interruption and reload tests to start early

### 3. Implement transcript loading and basic resume recovery

Land third:

- transcript reader/loader
- reconstruction of the effective conversation state
- basic invalid-record sanitization and partial-turn handling
- resume-facing API or CLI integration

Why third:

- this converts persistence from write-only logging into an actual recovery feature
- it establishes the loader pipeline Phase 5 will later extend

### 4. Separate prompt history and harden resume semantics

Land fourth:

- explicit prompt-history storage and tests
- stronger resume coverage for interrupted sessions
- basic tombstone/repair handling where needed

Why fourth:

- by this point transcript persistence exists and can be contrasted against prompt history cleanly
- it closes the most important semantic confusion before more persistence features accumulate

### 5. Close out with runtime integration tests and documentation

Finish with:

- end-to-end tests using persisted sessions
- contributor-facing notes about what is durable and what is not
- review of deferred items against roadmap landing zones

## Suggested testing additions

Phase 3 should add or expand tests for at least:

- a session transcript being created only after meaningful persisted content exists
- append ordering within a transcript file
- reloading a persisted conversation into a new runtime/session object
- preserving committed user input across interruption
- recovery behavior for partial assistant output or interrupted turns
- prompt history remaining separate from transcript records
- at least one real resume path that uses on-disk persisted state rather than in-memory fixtures alone

## Deferred item landing zones

For clarity, the main items intentionally deferred by this note should land approximately here:

- broader model routing, fallback, and retry semantics -> **Phase 4**
- broader result-shaping and daily-driver robustness beyond this persistence baseline -> **Phase 4**
- compaction/checkpointing and long-session recovery hardening -> **Phase 5**
- background tasks and their durability model -> **Phase 6**
- worker/agent coordination persistence -> **Phase 7**
- MCP and ecosystem-backed persistence interactions -> **Phase 8**
- remote session/bridge-backed persistence and hydration -> **Phase 9**

## Bottom line

Phase 3 should establish Pinser’s first real durable session model.

The key discipline is to land a small but structurally correct persistence and resume layer now:

- append-oriented per-session transcript storage
- explicit separation of transcript persistence from prompt history
- early durable recording of committed user input
- a recovery loader that reconstructs a usable conversation rather than raw replay
- basic interruption and partial-output handling

while deferring compaction, long-session maintenance, and broader robustness work to the later phases where the roadmap already places them.
