# Transcript and persistence semantics for a clean-room rewrite

This document describes how conversation state is persisted, recovered, normalized, and resumed. It focuses on the behavioral contracts a clean-room rewrite must preserve around transcript durability, session files, tool-result persistence, subagent sidechains, remote hydration, compaction boundaries, and recovery from partial or malformed state.

This is one of the most important hidden compatibility areas in the system. A rewrite can appear correct in normal interactive use while still breaking:
- resume
- compaction recovery
- subagent resume
- prompt-cache stability
- remote session hydration
- tool/result pairing after interruptions
- title/tag/session metadata recovery

Companion docs:
- `docs/hld.md`
- `docs/interfaces-and-endpoints.md`
- `docs/task-and-swarm.md`
- `docs/permission-engine.md`
- `docs/implementation-notes-and-gotchas.md`

Primary inspected sources for this pass:
- `src/utils/sessionStorage.ts`
- `src/utils/conversationRecovery.ts`
- `src/utils/messages.ts`
- `src/utils/toolResultStorage.ts`
- `src/utils/mcpOutputStorage.ts`
- `src/tools/AgentTool/resumeAgent.ts`
- `src/utils/crossProjectResume.ts`

---

## 1. Purpose

The system persists far more than a simple chat log.

The persisted state is used to reconstruct:
- the API-visible conversation transcript
- resume/continue state
- tool-use / tool-result relationships
- session metadata shown in session pickers
- subagent transcripts and resumability
- content-replacement decisions for large tool results
- file-history and attribution side state
- context-collapse state
- remote/CCR-backed session continuity

A rewrite must therefore preserve two distinct things:

1. **durability semantics** — what gets written, when, and to which file
2. **reconstruction semantics** — how persisted state is interpreted on resume

---

## 2. Persistence model overview

## 2.1 Main transcript format
The primary local durability unit is a per-session JSONL transcript file.

Conceptually:
- one file per interactive session
- each line is one JSON object entry
- entries include transcript messages and non-message metadata/state entries

Session path shape is conceptually:

```text
<config>/projects/<sanitized-project-path>/<sessionId>.jsonl
```

### Rewrite requirement
Preserve:
- per-project session storage
- per-session append-only JSONL shape
- ability to scan by lines and recover partial data conservatively

---

## 2.2 Session file materialization is lazy
The system does **not** create a session transcript file immediately at startup.

Instead:
- metadata and non-message entries may be buffered in memory first
- the session file is materialized on the first real `user` or `assistant` message

Rationale:
- avoid empty/metadata-only session files
- avoid polluting resume history with sessions that never really started

### Rewrite requirement
Preserve lazy materialization semantics.

This matters for:
- `--no-session-persistence`
- cleanup/title persistence behavior
- avoiding orphan/no-op sessions in history

---

## 2.3 Transcript entries are not only messages
The JSONL file contains both:
- transcript messages
- auxiliary entries

Message entries:
- `user`
- `assistant`
- `attachment`
- `system`

Non-message entries include things like:
- `custom-title`
- `ai-title`
- `last-prompt`
- `tag`
- `agent-name`
- `agent-color`
- `agent-setting`
- `mode`
- `worktree-state`
- `pr-link`
- `file-history-snapshot`
- `attribution-snapshot`
- `queue-operation`
- `content-replacement`
- context-collapse entries (`marble-origami-*`)
- summaries / task summaries

### Rewrite requirement
Preserve the mixed-entry log model. Do not reduce the transcript to messages only.

---

## 3. Transcript chain model

## 3.1 Messages form a parent-linked chain
Transcript message entries carry chain metadata conceptually like:

```ts
type TranscriptMessage = Message & {
  uuid: string
  parentUuid: string | null
  logicalParentUuid?: string
  isSidechain?: boolean
  sessionId: string
  cwd: string
  version: string
  gitBranch?: string
  slug?: string
  promptId?: string
  agentId?: string
  teamName?: string
  agentName?: string
}
```

### Meaning
This is not just append order. The system reconstructs the active conversation by following the parent chain from a selected leaf.

### Rewrite requirement
Preserve parent-linked transcript reconstruction, not just line-order replay.

---

## 3.2 Chain participants exclude progress messages
`progress` messages are explicitly **not** transcript-chain participants.

They are UI-state messages, not durable conversation messages.

Implications:
- they must not be treated as part of the durable parent chain
- later messages must not point to progress entries as their `parentUuid`
- old transcripts that accidentally included progress must be bridged/recovered

### Rewrite requirement
Preserve the distinction between:
- persisted conversation entries
- ephemeral progress/UI state

This is critical.

---

## 3.3 Compact boundaries break the chain intentionally
A compact boundary message causes a deliberate chain break:
- `parentUuid` becomes `null`
- the prior chain link is preserved separately as `logicalParentUuid`

This lets resume and `--continue` start from the post-compaction slice rather than the entire historical transcript.

### Rewrite requirement
Preserve the difference between:
- physical transcript linkage
- logical ancestry across compaction

---

## 4. Write path semantics

## 4.1 Writes are buffered and batched
Local writes are not immediately fsynced one-by-one.
The system:
- queues entries per file
- batches them on a timer
- appends JSONL lines in chunks
- resolves per-entry promises after chunk write completion

### Why this matters
This reduces write amplification while keeping ordering per file.

### Rewrite requirement
Preserve:
- append ordering per file
- no reordering of entries within a file
- ability to flush outstanding writes on cleanup/shutdown

Exact buffering implementation may differ.

---

## 4.2 Flush and cleanup semantics
There is an explicit flush operation that:
- cancels pending timers
- waits for active drains to finish
- drains remaining queued writes
- waits for tracked non-queue operations

Cleanup also re-appends session metadata afterward so it remains visible in tail reads.

### Rewrite requirement
Preserve an explicit flush barrier and cleanup-time metadata re-append.

---

## 4.3 Session metadata is re-appended near EOF
Certain metadata entries are intentionally written again near the file tail:
- `custom-title`
- `tag`
- `last-prompt`
- agent metadata
- mode/worktree/PR metadata

Reason:
- lightweight session loading reads only the tail window
- without re-append, older metadata can fall out of the tail and disappear from resume listings

### Rewrite requirement
Preserve tail-visible metadata semantics.

This is subtle and important.

---

## 4.4 Metadata cache absorbs fresher external writes
Before re-appending metadata, the system rereads the transcript tail and updates in-memory cache for SDK-mutable fields like:
- title
- tag

This prevents stale local cache from overwriting a newer externally written value.

### Rewrite requirement
Preserve external-writer reconciliation for tail-metadata fields.

---

## 5. What is persisted locally vs not

## 5.1 Transcript messages are persisted
Durable message classes:
- `user`
- `assistant`
- `attachment`
- `system`

## 5.2 Progress is not part of durable transcript semantics
Although some legacy transcripts may contain progress-like entries, current intended behavior is:
- progress is UI-only
- it should not participate in transcript reconstruction

### Rewrite requirement
Preserve this durable/non-durable split.

---

## 5.3 Session persistence can be globally suppressed
Persistence is skipped under conditions such as:
- test mode unless explicitly enabled
- cleanup period effectively disabled
- explicit no-session-persistence mode
- environment flags suppressing prompt history

### Rewrite requirement
Preserve a central “should skip persistence” gate that all write paths respect.

---

## 6. Resume loading pipeline

## 6.1 Sources for resume
Resume can load from:
- most recent session
- specific session ID
- preloaded log metadata object
- explicit transcript `.jsonl` path

### Rewrite requirement
Preserve the ability to resume both by session identity and by direct transcript path.

This matters for cross-directory/cross-project resume.

---

## 6.2 Lite logs vs full logs
The system can first inspect lightweight session metadata, then load the full transcript only when necessary.

### Rewrite requirement
Preserve separation between:
- listing metadata for session picker/history
- full transcript reconstruction

---

## 6.3 Resume reconstruction pipeline
The effective resume pipeline is roughly:

1. load transcript/log entries
2. restore certain non-message state (skills, plans, file history, metadata)
3. migrate legacy attachment shapes
4. sanitize invalid enum-like persisted values
5. filter unresolved tool uses
6. filter orphaned thinking-only messages
7. filter whitespace-only assistant messages
8. detect interrupted-turn state
9. possibly append a synthetic continuation message
10. ensure ending role shape is API-valid by appending synthetic assistant sentinel if needed
11. run session-start hooks for resume
12. append hook-generated messages

### Rewrite requirement
Preserve this as a normalization-and-recovery pipeline, not a raw replay.

---

## 7. Interruption and continuation semantics

## 7.1 Interrupted prompt vs interrupted turn
The system distinguishes:
- **interrupted prompt**: user message exists but assistant had not meaningfully started
- **interrupted turn**: tool-result/attachment state indicates the turn was mid-flight

Internal detection may then normalize interrupted-turn into an interrupted-prompt-style continuation path by appending a synthetic user continuation message.

### Rewrite requirement
Preserve explicit interruption-state detection.

---

## 7.2 Synthetic continuation prompt
When a conversation is judged interrupted mid-turn, resume appends a synthetic user message like:

```text
Continue from where you left off.
```

This unifies later resume behavior.

### Rewrite requirement
Preserve synthetic continuation injection semantics when the turn was interrupted.

---

## 7.3 Synthetic assistant sentinel after trailing user message
If the normalized conversation ends with a user message, the loader inserts a synthetic assistant message carrying a no-response sentinel.

Purpose:
- keep the transcript API-valid if no immediate resume action happens
- allow later splice/removal operations to target a stable user+assistant pair

### Rewrite requirement
Preserve this API-validity sentinel behavior.

---

## 8. Tool-use / tool-result recovery semantics

## 8.1 Unresolved tool uses are filtered out on resume
If a `tool_use` has no matching `tool_result`, the assistant message containing that unresolved use is filtered out during recovery.

Important detail:
- tool-use/result detection is done directly from persisted message content
- recovery avoids generating fresh UUIDs while doing so

### Rewrite requirement
Preserve filtering of unresolved tool uses during resume.

This prevents invalid API histories and transcript growth pathologies.

---

## 8.2 Orphaned tool results are also repaired later
Independent of resume filtering, API-preparation code also enforces tool-use/tool-result pairing by:
- stripping orphaned `tool_result`s that have no matching `tool_use`
- synthesizing missing error tool_results for missing pairings
- optionally failing hard in strict mode instead of repairing

### Rewrite requirement
Preserve a final defensive pairing pass before API submission.

Resume normalization alone is not enough.

---

## 8.3 Strict mode for pairing mismatches
In some modes, pairing mismatches are not repaired but treated as fatal because synthetic placeholders would poison downstream data quality.

### Rewrite requirement
Preserve the ability to run in strict fail mode rather than always repairing.

---

## 8.4 Tool-result terminal-turn exceptions
A transcript ending on a tool result is **not always** an interrupted turn.
Some tools legitimately terminate the turn, such as user-message delivery tools in brief-like modes.

Resume detection therefore walks backward to the originating tool_use and checks whether the tool is a terminal-turn tool.

### Rewrite requirement
Preserve terminal-tool exceptions when judging interrupted sessions.

---

## 9. Assistant-content recovery semantics

## 9.1 Orphaned thinking-only assistant messages are removed
Streaming can produce standalone assistant messages containing only thinking/redacted-thinking blocks.
If no sibling assistant message with the same message-id contains non-thinking content, these thinking-only messages are removed.

### Why this matters
Otherwise API replay can fail due to invalid assistant/thinking structure.

### Rewrite requirement
Preserve orphaned-thinking filtering.

---

## 9.2 Whitespace-only assistant messages are removed
Assistant messages whose content is effectively only whitespace are removed.
If this removal leaves adjacent user messages, they are merged.

### Rewrite requirement
Preserve whitespace-only assistant filtering and post-filter user merging.

---

## 9.3 Empty non-final assistant messages need placeholders
When normalizing for API, non-final assistant messages are not allowed to have empty content arrays.
A placeholder is inserted when necessary.

### Rewrite requirement
Preserve final-API normalization for empty assistant content.

---

## 10. Message normalization for API

## 10.1 API-facing transcript is a transformed view
The persisted transcript is not sent to the API verbatim.
Normalization includes behaviors such as:
- merging adjacent user messages
- reordering attachments/tool-result neighborhoods
- merging assistant fragments with same message-id
- stripping unavailable tool references
- stripping unsupported fields depending on tool-search mode
- filtering/repairing invalid assistant content
- ensuring tool-result pairing
- adding/removing system-reminder wrappers and other structural cleanup

### Rewrite requirement
Preserve the idea of a distinct API-normalization layer.

---

## 10.2 Adjacent user messages merge for API semantics
The API-facing transcript cannot rely on consecutive user messages being legal in all backends, so adjacent user messages are merged.

This matters for:
- attachments
- tool results
- interruption recovery
- queued inputs
- compaction/normalization interactions

### Rewrite requirement
Preserve adjacent-user merge semantics in the API-facing transcript.

---

## 10.3 Tool results are hoisted before sibling content
Within merged user content arrays, `tool_result` blocks are hoisted before other content so the API sees valid tool-result ordering.

### Rewrite requirement
Preserve tool-result hoisting inside merged user messages.

---

## 11. Session metadata semantics

## 11.1 Important session metadata fields
Persisted session metadata includes at least:
- custom title
- AI-generated title
- last prompt
- tag
- agent name/color/setting
- mode
- worktree state
- PR linkage data

### Rewrite requirement
Preserve these as individually persisted recoverable session properties.

---

## 11.2 `last-prompt` is derived from meaningful user input
The system extracts a “meaningful first/last user prompt” rather than blindly using the first persisted user content.
It skips things like:
- meta-only messages
- compaction summaries
- many tagged/system-like payloads
- some built-in slash commands with no meaningful argument payload

### Rewrite requirement
Preserve semantic extraction of display-worthy prompt text rather than raw first-line logging.

---

## 11.3 Cross-project resume awareness
When resuming sessions from another project path:
- same-repo worktrees may be resumed directly
- different projects may require a generated `cd ... && pinser --resume ...` command

### Rewrite requirement
Preserve cross-project resume classification and worktree-aware special handling.

---

## 12. Subagent and sidechain persistence

## 12.1 Sidechains are persisted separately from main transcript
Agent/subagent sidechains are written to separate transcript files, typically under a session-scoped subagents area.

Conceptually:

```text
<project>/<sessionId>/subagents/.../agent-<agentId>.jsonl
```

### Rewrite requirement
Preserve separate sidechain transcript files for subagents.

---

## 12.2 Sidechain dedup semantics differ from main transcript dedup
Messages inherited from the parent may share UUIDs with main-session messages.
For local subagent sidechain persistence, dedup against main-session UUIDs must not incorrectly suppress these writes.

### Rewrite requirement
Preserve the distinction between:
- main transcript dedup
- sidechain local persistence behavior

This is a critical gotcha.

---

## 12.3 Remote persistence constraints differ from local sidechain constraints
In remote single-chain persistence contexts, replaying a UUID already known upstream can conflict, even if it would be acceptable locally in a separate file.

### Rewrite requirement
Preserve separate local-vs-remote dedup constraints.

---

## 12.4 Subagent metadata is stored in sidecar files
Subagents also persist metadata outside the transcript, including things like:
- agent type
- worktree path
- description

This is used by resume to:
- restore the correct agent type
- restore worktree cwd if still valid
- restore better display descriptions

### Rewrite requirement
Preserve subagent metadata sidecars separate from transcript body.

---

## 12.5 Resume of subagents reconstructs content-replacement state
On subagent resume, content-replacement state is reconstructed from:
- the resumed sidechain transcript
- sidechain content-replacement records
- inherited replacement mappings from the parent where needed

### Rewrite requirement
Preserve replacement-state reconstruction for resumed subagents.

---

## 13. Remote session hydration

## 13.1 Remote sessions can hydrate local transcript files
For remote/CCR-style sessions, the system can fetch remote logs/internal events and write them into local transcript files before enabling continued persistence.

### Rewrite requirement
Preserve a hydrate-before-continue model for remote sessions.

---

## 13.2 Two remote persistence styles exist
Observed styles:
- v1-like remote session ingress append/fetch model
- CCR v2 internal-event reader/writer model

### Rewrite requirement
Preserve the abstraction boundary: local transcript logic should be able to target either remote backend model.

---

## 13.3 Remote hydrate writes main and subagent transcripts
CCR v2 hydration reconstructs:
- foreground transcript
- per-subagent transcript files grouped by `agent_id`

### Rewrite requirement
Preserve remote ability to reconstruct both main and sidechain transcripts.

---

## 14. Tool-result persistence to disk

## 14.1 Large tool results are offloaded to session-local files
Large tool outputs are not always kept inline in model-visible transcript content.
Instead, oversized tool results may be persisted to disk under a session-scoped tool-results directory.

Conceptually:

```text
<project>/<sessionId>/tool-results/<toolUseId>.(txt|json|mime-derived-ext)
```

### Rewrite requirement
Preserve file-based offloading of large tool results.

---

## 14.2 Persisted-output message shape is part of the contract
When a large text result is offloaded, the visible tool_result content is replaced with a persisted-output wrapper that includes:
- that output was too large
- path to the full saved output
- preview text

### Rewrite requirement
Preserve the existence of a recognizable persisted-output replacement marker/wrapper.

Exact wording may vary; semantics should not.

---

## 14.3 Empty tool results are replaced with a synthetic non-empty marker
If a tool completes with empty/whitespace-only output, the system inserts a small synthetic marker like:

```text
(<toolName> completed with no output)
```

Reason:
- empty tool results at the prompt tail can trigger stop-sequence/model-turn pathologies

### Rewrite requirement
Preserve non-empty substitution for logically empty tool results.

---

## 14.4 Non-text content has special persistence rules
Some tool results cannot be offloaded through the generic text path, such as:
- images in tool_result blocks
- binary MCP outputs

These either:
- stay inline in model content when necessary
- or are persisted as raw binary blobs with mime-derived extensions

### Rewrite requirement
Preserve special handling for images/binary outputs and mime-aware raw persistence.

---

## 14.5 Persistence threshold is tool-aware and configurable
Large-result persistence threshold is not purely global:
- per-tool caps exist
- global clamps exist
- feature-config overrides may exist
- some tools effectively opt out (e.g. infinite threshold semantics)

### Rewrite requirement
Preserve threshold resolution as a function of tool identity plus configuration.

---

## 15. Aggregate tool-result budget semantics

## 15.1 There is a per-message aggregate budget, not only per-tool thresholds
Beyond individual tool result limits, the system enforces an aggregate budget across tool results that will appear in the same API-level user message.

This is important because multiple individually acceptable tool results may merge into one oversized API user turn.

### Rewrite requirement
Preserve aggregate budget enforcement on the API-normalized message grouping, not just on raw individual results.

---

## 15.2 Budget decisions are frozen by tool-use ID
For prompt-cache stability, each tool result’s replacement fate is frozen once seen:
- if previously replaced, the exact same replacement must be reapplied byte-for-byte
- if previously left unreplaced, it must not later become replaced

State is tracked by tool-use ID.

### Rewrite requirement
Preserve frozen replacement decisions keyed by tool-use ID.

This is a major invariant.

---

## 15.3 Replacement state is persisted separately in transcript
Replacement decisions are also recorded as transcript entries (`content-replacement`) so resume can reconstruct the same visible prompt bytes.

### Rewrite requirement
Preserve durable recording of content replacement decisions, not just ephemeral in-memory state.

---

## 15.4 Reconstructing replacement state freezes all seen candidate IDs
On resume, replacement-state reconstruction does two things:
- restores explicit stored replacements
- marks all candidate tool-result IDs in loaded messages as “seen,” even if no replacement record exists

This prevents newly replacing content the model already saw unreplaced.

### Rewrite requirement
Preserve this seen/frozen semantics during reconstruction.

---

## 16. MCP/binary output persistence

## 16.1 Binary blobs are stored as raw bytes, not JSON-stringified content
When binary MCP or related content is persisted, the bytes are written as-is using an extension derived from MIME type.

### Rewrite requirement
Preserve raw-byte persistence for binary artifacts.

---

## 16.2 The saved path itself is surfaced back to the model/user flow
The model is told where the binary/blob content was saved.

### Rewrite requirement
Preserve durable discoverability of offloaded binary content via path references.

---

## 17. Legacy compatibility and migration semantics

## 17.1 Legacy attachment types are migrated on read
Older persisted attachment types are mapped into current attachment shapes during recovery.

### Rewrite requirement
Preserve read-time migration hooks for legacy persisted transcript schemas.

---

## 17.2 Invalid persisted enum-like values are sanitized
For example, invalid persisted permission-mode values are stripped rather than trusted.

### Rewrite requirement
Preserve validation/sanitization of persisted fields rather than assuming disk data is valid.

---

## 17.3 Old progress-bearing transcripts require compatibility handling
Because old transcripts may contain progress entries in places no longer allowed, load/recovery code must bridge over them rather than assuming modern invariants always held.

### Rewrite requirement
Preserve backward-compatible read behavior for old transcript formats.

---

## 18. Compaction persistence semantics

## 18.1 Compact boundaries are durable transcript entries
Compaction is not just an in-memory rewrite. It emits explicit transcript entries that future resume logic uses to reconstruct the active suffix.

### Rewrite requirement
Preserve compaction as a durable transcript event.

---

## 18.2 Context-collapse state has its own append-only durable entries
The system persists context-collapse commit and snapshot entries separately from ordinary transcript messages.

### Rewrite requirement
Preserve append-only durable context-collapse state entries and last-wins snapshot semantics.

---

## 18.3 Resume should start from latest effective compacted chain
The loader does not simply replay all lines. It identifies the appropriate leaf and chain slice after compaction semantics are applied.

### Rewrite requirement
Preserve compact-aware transcript chain reconstruction.

---

## 19. Orphan/tombstone semantics

## 19.1 Tombstoning removes transcript entries by UUID
When an orphaned message needs to be removed, the transcript store can remove it by UUID.

Optimized behavior:
- try tail-window splice first
- fall back to full-file rewrite only when necessary
- skip expensive rewrite for overly large files

### Rewrite requirement
Preserve targeted message removal capability and size-aware fallback behavior.

---

## 19.2 Tombstoning is best-effort and size-aware
For huge transcript files, the system may intentionally skip expensive rewrite paths rather than risk OOM or extreme latency.

### Rewrite requirement
Preserve size-aware best-effort removal rather than insisting on full exact rewrites at any cost.

---

## 20. Session adoption and switching semantics

## 20.1 Resumed sessions are adopted, not recreated
After switching into a resumed session, the system points current session state at the existing transcript file and re-appends metadata there.

This is important when resuming then exiting before producing a new user message.

### Rewrite requirement
Preserve adopt-existing-session-file behavior after resume.

---

## 20.2 New session IDs vs resumed session IDs must not cross-contaminate metadata
Several subtle bugs are avoided by always stamping persisted messages and metadata with the actual active session identity and by updating project/session pointers atomically when switching.

### Rewrite requirement
Preserve atomic session switching and restamping semantics.

---

## 21. Important invariants for a rewrite

## 21.1 Transcript reconstruction is chain-based, not append-order-only
Failure mode:
- resume loads wrong branch or stale suffix

## 21.2 Progress must not participate in the durable chain
Failure mode:
- parent links point into ephemeral entries, orphaning real conversation

## 21.3 Resume is a repair pipeline, not a raw deserialize
Failure mode:
- unresolved tool uses, orphaned thinking, whitespace-only assistant content break API replay

## 21.4 Tool-use/tool-result pairing needs both recovery-time and API-time defense
Failure mode:
- interrupted sessions remain unrecoverable

## 21.5 Metadata must stay near EOF for lite session loading
Failure mode:
- titles/tags disappear from session picker after enough later writes

## 21.6 Sidechain transcripts are separate durability domains
Failure mode:
- subagent inherited context is dedup-dropped or resume loses fork context

## 21.7 Replacement decisions for large tool results must be frozen by tool-use ID
Failure mode:
- prompt-cache instability and resume divergence

## 21.8 Loaded replacement state must freeze unreplaced content too
Failure mode:
- resume newly replaces content the model originally saw inline

## 21.9 Empty tool results must become non-empty visible markers
Failure mode:
- tail-of-turn model stop-sequence pathologies

## 21.10 Remote hydration must reconstruct both main and subagent transcripts before continuing
Failure mode:
- resumed remote sessions lose sidechains or continue from incomplete state

---

## 22. Minimal behavioral surface for a rewrite

A compatible rewrite should expose facilities structurally like:

```ts
type SessionPersistence = {
  recordTranscript(messages: Message[], teamInfo?: TeamInfo): Promise<UUID | null>
  recordSidechainTranscript(messages: Message[], agentId?: string): Promise<void>
  recordContentReplacement(records: ContentReplacementRecord[], agentId?: AgentId): Promise<void>
  recordFileHistorySnapshot(...args): Promise<void>
  recordAttributionSnapshot(...args): Promise<void>
  recordContextCollapseCommit(...args): Promise<void>
  recordContextCollapseSnapshot(...args): Promise<void>

  flush(): Promise<void>
  removeTranscriptMessage(targetUuid: UUID): Promise<void>

  loadConversationForResume(
    source: string | LogOption | undefined,
    sourceJsonlFile?: string,
  ): Promise<LoadedConversation | null>

  hydrateRemoteSession(sessionId: string, ingressUrl: string): Promise<boolean>
  hydrateFromRemoteInternalEvents(sessionId: string): Promise<boolean>
}
```

And separately:

```ts
type ToolResultPersistence = {
  persistToolResult(content, toolUseId): Promise<PersistedToolResult | PersistError>
  processToolResultBlock(tool, result, toolUseId): Promise<ToolResultBlock>
  applyToolResultBudget(messages, state, writeToTranscript?): Promise<Message[]>
  reconstructContentReplacementState(messages, records, inherited?): ContentReplacementState
}
```

Exact names may differ; the behaviors should not.

---

## 23. What may vary vs what should stay close

## Preserve closely
- append-only JSONL transcript semantics
- chain-based reconstruction
- lazy session-file materialization
- metadata tail re-append
- resume normalization/repair pipeline
- subagent sidechain file separation
- content-replacement record persistence and reconstruction
- compaction boundary semantics
- hydrate-before-continue remote behavior
- best-effort tombstoning behavior

## Can vary somewhat
- exact file/directory naming details
- exact batching implementation
- exact preview wording for persisted outputs
- exact analytics emitted during repair/persistence flows
- exact low-level tail-scan implementation details

---

## 24. Confidence and limits

High confidence:
- the transcript persistence, metadata re-append, resume normalization, sidechain persistence, tool-result offloading, and replacement-state semantics are directly supported by inspected code
- many of these behaviors are clearly responses to real production bugs, not incidental implementation details

Lower confidence:
- this doc does not fully enumerate every lite-log optimization or every context-collapse restore detail
- some remote/CCR behavior depends on upstream services not fully inspected here

Even so, this should be a strong clean-room contract for re-implementing transcript durability, session recovery, and persistence semantics without copying the original implementation.