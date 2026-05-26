# Session compaction and recovery state machine for a clean-room rewrite

This document specifies the conversation-compaction and conversation-recovery semantics that a compatible rewrite should preserve. It focuses on the boundary between:
- the append-only transcript on disk
- the effective in-memory conversation after compaction, snip, and resume
- the recovery logic that reconstructs the latest usable chain from that transcript

It is intentionally broader than a plain “compact command” document. The critical compatibility surface is the state machine formed by:
- transcript append
- compaction boundary insertion
- preserved-segment relinking
- snip gap removal
- resume-time chain reconstruction
- interruption detection
- context-collapse sidecar restoration

Companion docs:
- `docs/transcript-and-persistence-semantics.md`
- `docs/message-normalization-for-api.md`
- `docs/agent-resume-and-sidechains.md`
- `docs/task-and-swarm.md`
- `docs/implementation-notes-and-gotchas.md`

Primary inspected sources for this pass:
- `src/utils/conversationRecovery.ts`
- `src/utils/sessionStorage.ts`
- `src/services/compact/compact.ts`
- `src/services/compact/sessionMemoryCompact.ts`
- `src/commands/compact/compact.ts`

---

## 1. Short answer to the naming question

No — this is not exactly the same thing as a hypothetical `docs/conversation-recovery-state-machine.md`.

The overlap is substantial, but the scopes are slightly different:

### `conversation-recovery-state-machine`
Would emphasize:
- resume-time loading
- transcript repair
- interruption detection
- latest-leaf selection
- cleanup and deserialization

### `session-compaction-and-recovery`
Also includes:
- how compaction writes boundaries and summaries
- how preserved segments are represented on disk
- how partial compaction changes recovery behavior
- how snip/compaction mutate the effective conversation without deleting old transcript lines
- how context-collapse metadata interacts with boundaries

So:
- **recovery-state-machine** = narrower, loader-centric
- **session-compaction-and-recovery** = broader, write+read state machine

Given the code, the broader document is the more useful one for a clean-room rewrite.

---

## 2. Why this matters

The transcript is append-only, but the effective conversation is not.

Over time, the runtime performs operations that change what the next model call should see:
- compact old history into a summary
- preserve only part of the old chain
- remove a middle range via snip
- restore a resumed chain after interruption
- ignore malformed/incomplete tail fragments
- recover auxiliary collapsed-state sidecars

A rewrite that only replays raw JSONL lines in file order will be wrong.

### Rewrite requirement
Treat recovery as a deterministic projection from append-only transcript to latest effective conversation, not as raw log replay.

---

## 3. High-level state machine

Conceptually the main conversation moves through these states:

```text
LIVE_APPEND
  -> COMPACT_WRITE
  -> POST_COMPACT_EFFECTIVE_VIEW
  -> MORE_APPENDS
  -> INTERRUPT_OR_EXIT
  -> RESUME_LOAD
  -> RECOVER_EFFECTIVE_CHAIN
  -> CLEAN_AND_DESERIALIZE
  -> LIVE_APPEND
```

And snip/context-collapse introduce additional transformations:

```text
LIVE_APPEND
  -> SNIP_WRITE
  -> EFFECTIVE_VIEW_WITH_GAPS_REMOVED

LIVE_APPEND
  -> CONTEXT_COLLAPSE_COMMIT_SIDECARS
  -> RESUME_RESTORE_COLLAPSE_STATE
```

The important point is that **disk state is historical**, while **recovered conversation is computed**.

---

## 4. Effective conversation after compaction

## 4.1 Compaction does not rewrite prior transcript lines in place
Compaction appends new transcript entries rather than editing or deleting earlier entries.

That means old pre-compact messages still physically exist on disk.

### Rewrite requirement
Preserve append-only transcript semantics even when compaction logically replaces old context.

---

## 4.2 Effective post-compact message ordering is structured
The compaction result conceptually builds a message list in this order:

```ts
type PostCompactMessages = [
  boundaryMarker,
  ...summaryMessages,
  ...messagesToKeep,
  ...attachments,
  ...hookResults,
]
```

This ordering is an important compatibility contract.

### Rewrite requirement
Preserve boundary → summary → kept messages → attachments → hook results ordering.

---

## 4.3 The runtime projects away messages before the latest compact boundary
At runtime, before later compaction/recovery operations, the system often reasons only about messages after the latest compact boundary.

### Rewrite requirement
Preserve the notion of “messages after latest compact boundary” as the effective active window.

---

## 5. Compact boundary semantics

## 5.1 Compaction writes an explicit boundary marker
Every compaction writes a synthetic system boundary message identifying that a compaction event occurred.

Boundary metadata includes at least:
- trigger kind (`manual` / `auto`)
- token count before compaction
- reference to the pre-compact tail / previous logical anchor
- optional extra metadata such as preserved-segment info and discovered-tool state

### Rewrite requirement
Preserve explicit compact-boundary messages as first-class transcript entries.

---

## 5.2 The summary is stored as a synthetic user message after the boundary
The compact summary is persisted as a user message flagged as a compact summary.

Important properties:
- it is synthetic/runtime-generated
- it is marked as compact-summary content
- in some paths it is transcript-visible-only

### Rewrite requirement
Preserve compact summaries as explicit structured messages, not opaque loader metadata.

---

## 5.3 The boundary may carry pre-compact discovered-tool state
Compaction records discovered/loaded deferred-tool names on the boundary so the post-compact system can keep tool availability/schema behavior consistent even though the old tool-reference blocks are gone.

### Rewrite requirement
Preserve boundary-carried tool-discovery state or an equivalent mechanism.

---

## 6. Full compaction semantics

## 6.1 Full compaction replaces the prior active history with boundary + summary + post-compact attachments/hooks
In the normal full-compaction path, the resulting active context is effectively:
- compact boundary
- one compact summary
- post-compact synthetic attachments/instructions
- session-start/post-compact hook messages

Unlike partial compaction, it generally does not preserve a suffix or prefix of the previous active conversation as ordinary kept messages.

### Rewrite requirement
Preserve the “summary replaces older active history” behavior for full compaction.

---

## 6.2 Full compaction re-announces context needed after history loss
Because compaction deletes prior in-context detail from the active window, the runtime re-attaches or re-announces things such as:
- recently read file summaries/stubs
- active plan attachment
- async/agent attachments if relevant
- deferred tool delta attachment(s)
- agent listing delta attachment(s)
- MCP instructions delta attachment(s)
- session-start hook outputs

### Rewrite requirement
Preserve explicit post-compact context rehydration for capabilities and state that were formerly only present in old messages.

---

## 6.3 Metadata is re-appended after compaction
After compaction, session metadata such as custom title/tag is re-appended so tail-window metadata readers still find it.

### Rewrite requirement
Preserve post-compaction restamping/reappending of tail-sensitive session metadata.

---

## 7. Partial compaction semantics

## 7.1 Partial compaction has two distinct directions
Partial compaction is not one thing. It has two modes:

```ts
type PartialCompactDirection = 'from' | 'up_to'
```

Semantics:
- `from`: summarize messages after pivot, keep earlier ones
- `up_to`: summarize messages before pivot, keep later ones

### Rewrite requirement
Preserve the two-direction partial-compaction model.

---

## 7.2 Partial compaction changes cache and ordering semantics depending on direction
Behavior differs materially:
- `from` is prefix-preserving
- `up_to` is suffix-preserving

This affects:
- which messages are kept
- where the summary sits relative to the kept segment
- which anchor UUID the preserved segment must relink to
- prompt-cache behavior

### Rewrite requirement
Preserve direction-specific semantics; do not collapse both modes into one generic summarization feature.

---

## 7.3 `up_to` strips older compact boundaries and compact summaries from the kept suffix
When preserving the suffix (`up_to`), stale earlier boundaries/summaries must be removed from the kept tail, otherwise backward boundary scans can select the wrong boundary and discard the new summary.

### Rewrite requirement
Preserve stale-boundary/stale-summary stripping from kept suffixes in prefix-summarizing partial compact.

---

## 7.4 Progress messages are excluded from kept segments
Progress messages are not safe anchoring points for later parent-chain reconstruction and are excluded from kept segments.

### Rewrite requirement
Preserve progress-message exclusion in partial-compaction kept sets.

---

## 8. Preserved-segment relink semantics

## 8.1 Kept messages are not physically rewritten to new parent UUIDs on disk
When a partial/session-memory compact preserves a message segment, those kept messages remain in the transcript with their old parent links.

This means the loader must reconstruct the intended post-compact chain later.

### Rewrite requirement
Preserve read-time relinking for preserved segments unless the rewrite chooses to physically rewrite the kept segment at write time.

---

## 8.2 The compact boundary stores enough relink metadata to restore the intended chain
A preserved segment is described by three UUIDs:

```ts
type PreservedSegment = {
  headUuid: string
  anchorUuid: string
  tailUuid: string
}
```

Where:
- `headUuid` = first kept message in the preserved segment
- `tailUuid` = last kept message in the preserved segment
- `anchorUuid` = what should conceptually precede the kept segment after compaction

Anchor semantics:
- suffix-preserving compact: anchor is the last summary message
- prefix-preserving compact: anchor is the boundary itself

### Rewrite requirement
Preserve enough relink metadata for a loader to splice kept segments back into the effective chain.

---

## 8.3 Only the latest live preserved segment is relinked
If there were multiple compactions over time, only the preserved segment associated with the absolute latest live boundary is treated as active.

If a later boundary exists without preserved-segment metadata, an older preserved-segment entry is considered stale and is not relinked.

### Rewrite requirement
Preserve last-live-boundary precedence for preserved-segment relinking.

---

## 8.4 Relinking requires validating the stored tail→head walk before mutation
Before mutating parent links in memory, the loader validates that it can walk backward from `tailUuid` to `headUuid` through existing transcript messages.

If the walk is broken, the relink becomes a no-op and the loader falls back to a safer larger-history view rather than constructing a malformed chain.

### Rewrite requirement
Preserve validation-before-relink behavior.

---

## 8.5 Relinking performs two splice operations
If valid, the loader performs the equivalent of:
- patch `head.parentUuid = anchorUuid`
- redirect any other children of `anchorUuid` to instead point at `tailUuid`

This creates the intended logical chain across the preserved segment.

### Rewrite requirement
Preserve both head splice and tail splice semantics.

---

## 8.6 Pre-boundary non-preserved messages are pruned after relink
After preserved-segment relinking, everything physically before the absolute latest boundary is deleted from the in-memory message map except messages explicitly belonging to the preserved set.

### Rewrite requirement
Preserve prune-after-relink behavior.

---

## 8.7 Preserved assistant usage counters are zeroed on load
Preserved assistant messages may still contain old on-disk usage numbers reflecting pre-compact context sizes. These are zeroed during relink/recovery so resume/autocompact logic does not misinterpret them as current huge-context usage.

### Rewrite requirement
Preserve stale-usage neutralization for preserved assistant messages.

This is a subtle but important operational invariant.

---

## 9. Session-memory compaction semantics

## 9.1 Session-memory compaction is still represented as compact boundary + summary + kept messages
Even though the summary source differs, session-memory compact produces the same logical shape:
- boundary
- summary message
- optionally preserved kept messages
- attachments/hook results

### Rewrite requirement
Preserve shared post-compact structural semantics across normal and session-memory compaction.

---

## 9.2 Session-memory compaction also uses preserved-segment annotation when keeping recent messages
If recent unsummarized messages are kept, the boundary is annotated with preserved-segment metadata using the last summary message as the anchor.

### Rewrite requirement
Preserve relink metadata for session-memory compaction just like other preserved compaction paths.

---

## 9.3 Session-memory compaction respects the latest compact boundary as a floor when growing a kept suffix
When selecting a recent window to keep, the algorithm does not expand backward across the latest compact boundary.

### Rewrite requirement
Preserve boundary-aware floor semantics when selecting kept messages after previous compaction.

---

## 10. Snip semantics

## 10.1 Snip removes middle ranges logically, not physically
Snip operations can remove an interior range from the effective conversation while leaving those transcript entries physically present on disk.

### Rewrite requirement
Preserve logical-removal vs physical-retention semantics for snip-like operations.

---

## 10.2 Snip writes exact removed UUIDs into boundary metadata
The loader relies on boundary metadata listing exactly which UUIDs were removed.

### Rewrite requirement
Preserve exact removed-UUID recording for middle-range deletions.

---

## 10.3 Resume deletes snipped messages from the in-memory map and relinks survivors across the gap
On load:
- marked removed UUIDs are deleted from the working message map
- any remaining message whose parent points into the removed set is relinked backward to the nearest surviving ancestor

### Rewrite requirement
Preserve delete-and-relink semantics for snipped gaps.

---

## 10.4 Missing historical snip metadata degrades to old behavior
Older transcripts without explicit removed-UUID metadata cannot be perfectly replayed, so the loader falls back to a less precise pre-fix behavior rather than crashing.

### Rewrite requirement
Preserve graceful degradation for older transcripts lacking modern snip metadata.

---

## 11. Transcript-load reconstruction semantics

## 11.1 Recovery starts from a parsed transcript map, not file-order replay
The loader parses transcript entries into structures such as:
- message map keyed by UUID
- metadata maps keyed by sessionId or messageId
- replacement records
- collapse commits/snapshots
- leaf UUID set

### Rewrite requirement
Preserve map-based transcript reconstruction instead of naive sequential replay.

---

## 11.2 The loader may skip obviously stale pre-boundary bytes for large transcripts
For large transcript files, the loader can optimize by skipping earlier pre-boundary content and separately scanning only the metadata needed from that older range.

### Rewrite requirement
A rewrite may vary the optimization mechanism, but should preserve the same logical result:
- old pre-boundary message bodies need not be fully loaded
- old session metadata still must be recoverable

---

## 11.3 Some metadata written before the latest boundary must still survive resume
Even when earlier message bodies are skipped, the loader still recovers session-scoped metadata such as:
- custom title
- tag
- agent name/color/setting
- mode
- worktree state
- PR link metadata

### Rewrite requirement
Preserve separate recovery of session-scoped metadata from pruned/skipped pre-boundary transcript ranges.

---

## 11.4 Compact boundaries clear stale context-collapse sidecar state during transcript load
When the loader encounters a compact boundary, previously accumulated context-collapse commits/snapshots from earlier ranges are discarded because those older spans are no longer part of the active resumed conversation.

### Rewrite requirement
Preserve boundary-driven invalidation of stale context-collapse sidecars.

---

## 12. Chain reconstruction semantics

## 12.1 Recovery uses leaf-based parent-chain reconstruction
The effective conversation is rebuilt by selecting a leaf message and walking `parentUuid` backward to the root, then reversing the result.

### Rewrite requirement
Preserve parent-chain reconstruction from a chosen leaf, not simple file-order replay.

---

## 12.2 The chosen leaf is the latest relevant user/assistant leaf, not necessarily the last physical transcript line
System/attachment/progress lines may trail the effective conversation. Leaf choice is based on terminal chain semantics, not file tail position alone.

### Rewrite requirement
Preserve semantic leaf selection for conversation recovery.

---

## 12.3 Recovery must handle legacy progress nodes in parent chains
Older transcripts may contain progress entries in the parent chain. The loader bridges through them so they do not truncate the conversation walk.

### Rewrite requirement
Preserve progress-bridge handling for old transcripts or provide an equivalent migration.

---

## 13. Parallel tool-use recovery semantics

## 13.1 The raw transcript topology may be a DAG, not a pure linked list
Streaming can emit multiple assistant fragments with the same logical assistant message ID and parallel tool uses/results that branch the parent topology.

A simple single-parent walk can drop siblings and some tool results.

### Rewrite requirement
Preserve post-walk recovery of orphaned sibling assistant/tool-result branches.

---

## 13.2 Recovery groups assistant fragments by logical assistant message ID
After the main chain walk, the loader groups assistant fragments sharing the same logical message ID and recovers off-chain siblings plus their tool results.

### Rewrite requirement
Preserve assistant-fragment sibling recovery semantics.

---

## 13.3 Recovered siblings/tool-results are inserted after the last on-chain member of that assistant group
This preserves group contiguity and ensures tool results remain after their corresponding tool uses.

### Rewrite requirement
Preserve insertion ordering for recovered parallel tool-use branches.

---

## 14. Resume cleanup / deserialization semantics

## 14.1 Raw loaded messages are not used directly
After chain reconstruction, the system deserializes/normalizes the recovered transcript by applying cleanup filters.

### Rewrite requirement
Preserve a cleanup-and-deserialize phase between chain recovery and resumed execution.

---

## 14.2 Cleanup removes unresolved tool uses and dependent synthetic tails
If an assistant tool use never received a matching result, that incomplete tail is removed before resume.

### Rewrite requirement
Preserve unresolved-tool-use filtering before resumed execution.

---

## 14.3 Cleanup removes orphaned thinking-only assistant fragments
Some streaming/interleaving patterns can leave assistant thinking fragments that would make the resumed transcript API-invalid.

### Rewrite requirement
Preserve orphaned-thinking-only filtering.

---

## 14.4 Cleanup removes whitespace-only assistant messages
Whitespace-only assistant fragments can appear after interrupted streaming and should not survive into resumed API input.

### Rewrite requirement
Preserve whitespace-only-assistant filtering.

---

## 15. Turn interruption detection semantics

## 15.1 Resume distinguishes no interruption, interrupted prompt, and interrupted turn
Conceptually:

```ts
type TurnInterruptionState =
  | { kind: 'none' }
  | { kind: 'interrupted_prompt'; message: UserMessage }
```

Internally there is also an `interrupted_turn` detection step that is transformed into an interrupted prompt by appending a synthetic continuation message.

### Rewrite requirement
Preserve turn-interruption classification rather than always blindly appending a continuation prompt.

---

## 15.2 Interruption detection ignores bookkeeping/system/progress noise
The last relevant message is computed by skipping system/progress messages and certain synthetic API-error assistant entries.

### Rewrite requirement
Preserve “last turn-relevant message” semantics for interruption detection.

---

## 15.3 A trailing assistant after cleanup usually means the turn completed
Because persisted streaming messages may not carry final stop reasons, the loader infers completion from the fact that unresolved tool uses were already filtered away.

### Rewrite requirement
Preserve assistant-tail-means-complete semantics after cleanup.

---

## 15.4 A trailing plain user message means interrupted prompt
If the last relevant message is a non-meta, non-compact-summary plain user message, the assistant never started responding.

### Rewrite requirement
Preserve interrupted-prompt detection for trailing ordinary user prompts.

---

## 15.5 A trailing tool-result user message is usually interrupted-turn, except for terminal tools
A conversation ending on a tool result usually indicates interruption mid-turn.
But some tools are legitimate terminal actions for a completed turn.

### Rewrite requirement
Preserve tool-specific terminal-tool-result exceptions in interruption detection.

---

## 15.6 Interrupted turns are normalized into an appended synthetic continuation user message
If interruption is detected mid-turn rather than mid-prompt, the loader appends a synthetic meta user message equivalent to:

```text
Continue from where you left off.
```

The public resume state then becomes `interrupted_prompt` with that synthetic message.

### Rewrite requirement
Preserve interrupted-turn → synthetic-continuation transformation.

---

## 15.7 If the final relevant message is user, a synthetic assistant sentinel is appended for API validity
Even if resume does not immediately continue, the loader inserts a synthetic assistant “no response requested” sentinel after a trailing user message so the transcript remains API-valid.

### Rewrite requirement
Preserve assistant-sentinel insertion after trailing user messages.

---

## 16. Legacy data migration semantics on resume

## 16.1 Attachment types are migrated during deserialization
Older attachment variants are transformed to current semantic attachment types and given backfilled display paths.

### Rewrite requirement
Preserve runtime migration of old persisted attachment variants.

---

## 16.2 Invalid persisted permission modes are stripped during load
User messages may contain unvalidated historical permission mode strings from older/different builds. Invalid values are cleared during deserialization.

### Rewrite requirement
Preserve invalid-permission-mode stripping on load.

---

## 16.3 Invoked skills and skill-listing latches are restored from transcript attachments before resume
The loader rehydrates skill-related process state from transcript attachments so later compactions/resumes do not lose that context or re-announce it unnecessarily.

### Rewrite requirement
Preserve transcript-driven restoration of skill state and “already announced” latches.

---

## 17. Context-collapse sidecar restoration semantics

## 17.1 Context-collapse commits are append-only sidecar entries
Collapsed archived messages are not separately duplicated inside the sidecar. Instead the transcript stores enough metadata to reconstruct the splice/boundaries and summary placeholder identity.

### Rewrite requirement
Preserve sidecar-based collapse commit persistence rather than duplicating archived payloads.

---

## 17.2 Context-collapse snapshot is last-wins staged-state persistence
The staged queue and spawn-trigger state are persisted as a snapshot where the most recent snapshot supersedes older ones.

### Rewrite requirement
Preserve last-wins semantics for staged collapse snapshot state.

---

## 17.3 Resume filters collapse sidecars to the resumed session
When a transcript is loaded for a particular session, only collapse entries belonging to that session are restored.

### Rewrite requirement
Preserve session-scoped filtering of collapse sidecar state.

---

## 17.4 Compact boundaries invalidate older collapse sidecars that no longer match the active post-compact conversation
Older collapse sidecars before the active boundary are discarded during transcript load.

### Rewrite requirement
Preserve boundary-aware collapse-sidecar invalidation.

---

## 18. Metadata and auxiliary state recovered with the conversation

A compatible recovery pipeline should restore, when available:

```ts
type ResumeLoadResult = {
  messages: Message[]
  turnInterruptionState: TurnInterruptionState
  fileHistorySnapshots?: FileHistorySnapshot[]
  attributionSnapshots?: AttributionSnapshotMessage[]
  contentReplacements?: ContentReplacementRecord[]
  contextCollapseCommits?: ContextCollapseCommitEntry[]
  contextCollapseSnapshot?: ContextCollapseSnapshotEntry
  sessionId?: string
  agentName?: string
  agentColor?: string
  agentSetting?: string
  customTitle?: string
  tag?: string
  mode?: 'coordinator' | 'normal'
  worktreeSession?: PersistedWorktreeSession | null
  prNumber?: number
  prUrl?: string
  prRepository?: string
  fullPath?: string
}
```

Exact type names may differ. The restored semantic fields should stay close.

---

## 19. Minimal recovery/compaction interfaces for a rewrite

A clean-room rewrite should preserve interfaces roughly like:

```ts
type CompactionResult = {
  boundaryMarker: Message
  summaryMessages: Message[]
  messagesToKeep?: Message[]
  attachments: Message[]
  hookResults: Message[]
}

type PreservedSegment = {
  headUuid: string
  anchorUuid: string
  tailUuid: string
}

type TranscriptLoader = {
  loadTranscriptFile(path: string): Promise<{
    messages: Map<string, TranscriptMessage>
    leafUuids: Set<string>
    contentReplacements: Map<string, ContentReplacementRecord[]>
    contextCollapseCommits: ContextCollapseCommitEntry[]
    contextCollapseSnapshot?: ContextCollapseSnapshotEntry
  }>

  buildConversationChain(
    messages: Map<string, TranscriptMessage>,
    leaf: TranscriptMessage,
  ): TranscriptMessage[]

  applyPreservedSegmentRelinks(
    messages: Map<string, TranscriptMessage>,
  ): void

  applySnipRemovals(
    messages: Map<string, TranscriptMessage>,
  ): void
}

type ResumeDeserializer = {
  deserializeMessagesWithInterruptDetection(
    serializedMessages: Message[],
  ): {
    messages: Message[]
    turnInterruptionState: TurnInterruptionState
  }
}
```

Exact names may vary. The behavioral contracts should not.

---

## 20. Critical invariants for a rewrite

## 20.1 Append-only transcript does not equal effective conversation
Failure mode:
- resume replays too much history or the wrong branch

## 20.2 The latest active compact boundary defines the effective pre/post split
Failure mode:
- stale pre-compact history re-enters the resumed conversation

## 20.3 Preserved segments must be relinked in memory or rewritten equivalently
Failure mode:
- kept suffix/prefix messages disappear or connect to the wrong anchor

## 20.4 Relinking must validate tail→head integrity before mutation
Failure mode:
- malformed preserved metadata corrupts the resumed chain

## 20.5 Snipped ranges must be deleted and survivors relinked across the gap
Failure mode:
- removed conversation ranges silently reappear on resume

## 20.6 Recovery must repair DAG-like parallel tool-use topology beyond a simple parent walk
Failure mode:
- sibling tool results vanish from resumed context

## 20.7 Cleanup must remove unresolved tool uses, orphaned thinking, and whitespace assistants
Failure mode:
- resumed transcript is API-invalid or semantically misleading

## 20.8 Interrupted turns must normalize to a synthetic continuation prompt
Failure mode:
- resume stalls or resumes from the wrong place

## 20.9 Post-compaction metadata must be restamped/reappended near transcript tail
Failure mode:
- resume/UI metadata readers lose custom title/tag/worktree state visibility

## 20.10 Compact boundaries must invalidate stale context-collapse sidecars from older ranges
Failure mode:
- restored collapse state references transcript spans no longer in active conversation

## 20.11 Preserved assistant usage must not retain stale pre-compact token counts
Failure mode:
- immediate bogus autocompact/recompact behavior on resume

---

## 21. What can vary vs what should stay close

## Preserve closely
- explicit compact boundary messages
- explicit compact summary messages
- boundary metadata for preserved segments
- last-live-boundary semantics
- in-memory relink + prune behavior
- snip delete-and-relink behavior
- leaf-based chain reconstruction
- orphaned parallel tool-result recovery
- interruption detection and synthetic continuation behavior
- boundary-aware invalidation of old collapse sidecars
- metadata recovery from skipped pre-boundary regions

## Can vary somewhat
- exact threshold/optimization strategy for skipping large pre-boundary transcript regions
- exact compact-summary wording
- exact telemetry events and counters
- exact data structures used internally for relinking
- whether rewrites preserve read-time relinking or instead physically rewrite kept-segment parent links at write time

---

## 22. Confidence and limits

High confidence:
- the boundary/summarize/kept-message structure, preserved-segment relinking, snip gap handling, chain recovery, interruption detection, and collapse-sidecar invalidation are directly supported by inspected code
- these are implementation-critical invariants, not just incidental choices

Lower confidence:
- some context-collapse internals live in other modules and are only described here from the session-storage interaction surface
- some optimization details may be more flexible than the current implementation suggests

Still, this document should be a strong clean-room contract for rebuilding the compaction/recovery pipeline without copying the original source.