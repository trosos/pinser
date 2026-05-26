# Conversation recovery state machine for a clean-room rewrite

This document isolates the **loader/resume side** of conversation reconstruction.

It is intentionally narrower than `docs/session-compaction-and-recovery.md`.
That broader document covers both write-time and read-time behavior. This one focuses specifically on the state machine that turns persisted transcript material into the effective resumed conversation.

Use this document when reimplementing:
- `--resume` / `--continue` conversation loading
- transcript deserialization and cleanup
- interruption detection
- latest-chain selection
- recovery of malformed or partially written conversation tails

Companion docs:
- `docs/session-compaction-and-recovery.md`
- `docs/transcript-and-persistence-semantics.md`
- `docs/message-normalization-for-api.md`
- `docs/agent-resume-and-sidechains.md`

Primary inspected sources for this pass:
- `src/utils/conversationRecovery.ts`
- `src/utils/sessionStorage.ts`

---

## 1. Scope

This document is about the recovery pipeline:

```text
persisted transcript
  -> transcript load
  -> chain selection/reconstruction
  -> repair/relink passes
  -> cleanup/deserialization
  -> interruption classification
  -> resumed in-memory conversation
```

It is not primarily about:
- how compaction summaries are generated
- how hooks run during compaction
- how post-compact attachments are synthesized
- how agent resume differs from main-thread resume

Those are documented elsewhere.

---

## 2. Core idea

Resume is not “read all transcript lines and continue”.

Resume is:
1. load persisted transcript structures
2. select the effective conversation branch
3. repair historical artifacts and append-only mismatches
4. remove incomplete or invalid tail fragments
5. classify whether the prior turn was interrupted
6. produce an API-safe in-memory message list

### Rewrite requirement
Preserve recovery as a deterministic projection from persisted transcript state to effective resumed conversation state.

---

## 3. Inputs to the recovery state machine

The loader can recover from multiple sources:
- no explicit source → most recent resumable session
- explicit session ID
- already loaded log object
- transcript JSONL path

Conceptually:

```ts
type ResumeSource =
  | undefined
  | string // session ID
  | LogOption
  | { jsonlPath: string }
```

### Rewrite requirement
Preserve support for both session-ID-based and direct-transcript-path-based recovery.

---

## 4. High-level recovery pipeline

A compatible recovery pipeline looks roughly like this:

```ts
async function loadConversationForResume(source): Promise<ResumeLoadResult | null> {
  const loaded = await resolveResumeSource(source)
  if (!loaded) return null

  const transcriptState = await loadTranscriptStructures(loaded)
  const recoveredChain = reconstructEffectiveChain(transcriptState)
  restoreProcessStateFromRecoveredMessages(recoveredChain)
  const deserialized = deserializeMessagesWithInterruptDetection(recoveredChain)
  const hookMessages = await processSessionStartHooksForResume()

  return {
    messages: [...deserialized.messages, ...hookMessages],
    turnInterruptionState: deserialized.turnInterruptionState,
    ...otherRecoveredMetadata,
  }
}
```

Exact decomposition may vary. The behavior should stay close.

---

## 5. Source resolution semantics

## 5.1 `undefined` means resume the most recent continuable session
When no source is specified, the loader finds the most recent session log suitable for continuation.

### Rewrite requirement
Preserve “no explicit source = most recent resumable session” behavior.

---

## 5.2 Live background/daemon sessions may be excluded from “most recent” selection
The recovery logic excludes certain live non-interactive/background sessions from normal `--continue` selection so it does not attach to a session that is still actively writing its own transcript.

### Rewrite requirement
Preserve skip-live-background-session logic for implicit resume/continue.

---

## 5.3 A direct JSONL path is recovered by chain-walking that file, not by treating it as a session ID
When the source is a transcript path, the loader walks that transcript file directly and reconstructs the main chain from its latest relevant leaf.

### Rewrite requirement
Preserve direct transcript-path recovery as a first-class path.

---

## 5.4 Already-loaded “lite” logs must be inflated before recovery
If the selected log is a lite metadata-only record, the full transcript/log content must be loaded before recovery proceeds.

### Rewrite requirement
Preserve full-log inflation before transcript recovery.

---

## 6. Transcript structure loading semantics

## 6.1 Recovery starts from transcript structures, not message arrays alone
The loader constructs several structures from disk, not just a message array.

At minimum it needs:
- transcript messages keyed by UUID
- leaf UUIDs
- session-scoped metadata maps
- content replacement records
- context-collapse sidecars
- file-history and attribution sidecars

### Rewrite requirement
Preserve structured transcript loading before recovery.

---

## 6.2 Recovery may optimize large transcripts by skipping stale pre-boundary content
Large transcript files may be loaded with a skip strategy that avoids reading or fully parsing obviously stale pre-boundary message bodies while still recovering needed metadata.

### Rewrite requirement
Preserve logical equivalence of recovered state even if the large-file optimization strategy differs.

---

## 6.3 Legacy progress entries are bridged during transcript load
Older transcripts can include progress entries in the parent chain. The loader records progress→parent relationships and rewrites later message parent links that point at progress entries.

### Rewrite requirement
Preserve bridging or migration of legacy progress-parent chains.

---

## 7. Effective-chain reconstruction semantics

## 7.1 Recovery reconstructs a chain from a leaf, not by file-order replay
The effective conversation is obtained by selecting a leaf message and walking the `parentUuid` chain backward to root.

### Rewrite requirement
Preserve parent-chain reconstruction semantics.

---

## 7.2 The selected leaf is a semantic user/assistant leaf
Leaf selection is based on the nearest relevant user/assistant endpoint of a conversation branch, not simply the last JSONL line.

### Rewrite requirement
Preserve semantic leaf selection for resumed conversation recovery.

---

## 7.3 Trailing metadata/system/progress entries must not steal leaf selection
Trailing non-conversation entries are bookkeeping artifacts and must not become the recovered conversation tip.

### Rewrite requirement
Preserve leaf selection that ignores non-turn-ending bookkeeping entries.

---

## 8. Read-time repair passes before final chain use

## 8.1 Preserved-segment relinking may mutate the in-memory transcript map before chain walk
If the latest compact boundary includes preserved-segment metadata, the loader first rewires the in-memory parent relationships so the intended post-compact chain is reconstructable.

### Rewrite requirement
Preserve pre-chain-walk relink repair for preserved compact segments.

---

## 8.2 Snip removals may mutate the in-memory transcript map before chain walk
If transcript metadata indicates logically removed UUID ranges, the loader deletes those messages from the working map and relinks surviving descendants to the first surviving ancestor.

### Rewrite requirement
Preserve pre-chain-walk snip repair.

---

## 8.3 Recovery should prefer safe no-op fallback over malformed repair
If repair metadata is inconsistent or incomplete, the loader should degrade to a larger-but-safe recovered history rather than corrupting the effective chain.

### Rewrite requirement
Preserve safety-first repair fallback semantics.

---

## 9. Parallel tool-use recovery semantics

## 9.1 A simple parent walk is insufficient for some persisted assistant/tool-result topologies
Streaming can produce DAG-like shapes where multiple assistant fragments share one logical assistant message and tool results hang from different sibling fragments.

### Rewrite requirement
Preserve a post-walk orphan recovery pass for parallel tool-use branches.

---

## 9.2 Recovery groups assistant fragments by logical assistant message identity
The loader identifies assistant fragments that belong to the same logical assistant message and treats them as a sibling group.

### Rewrite requirement
Preserve sibling-group recovery keyed by logical assistant message identity.

---

## 9.3 Recovered siblings and tool results are inserted after the last on-chain member of the group
This keeps the logical assistant group contiguous and ensures tool results remain after tool uses.

### Rewrite requirement
Preserve sibling/tool-result insertion ordering.

---

## 10. Deserialization and cleanup semantics

## 10.1 The reconstructed chain is still not directly safe to resume from
After chain reconstruction, the message list must still be deserialized and cleaned.

### Rewrite requirement
Preserve a cleanup phase after chain recovery and before resumed execution.

---

## 10.2 Legacy attachment variants are migrated during deserialization
Older persisted attachment formats are upgraded into the current semantic attachment types and have display paths backfilled if necessary.

### Rewrite requirement
Preserve attachment migration during recovery.

---

## 10.3 Invalid persisted permission-mode values are stripped during load
User messages may contain permission mode values not valid in the current build. Those invalid values are cleared.

### Rewrite requirement
Preserve invalid persisted permission-mode stripping.

---

## 10.4 Unresolved tool uses are filtered out before resume
If the transcript ends with assistant tool-use content that never received a matching tool result, that incomplete structure is removed.

### Rewrite requirement
Preserve unresolved-tool-use filtering before resumed API use.

---

## 10.5 Orphaned thinking-only assistant fragments are filtered out
Streaming/interleaving artifacts can leave isolated assistant thinking fragments that would be invalid or misleading if replayed.

### Rewrite requirement
Preserve orphaned-thinking-only filtering.

---

## 10.6 Whitespace-only assistant messages are filtered out
Interrupted streaming may leave assistant fragments containing only whitespace text. These are removed.

### Rewrite requirement
Preserve whitespace-only-assistant filtering.

---

## 11. Interruption classification state machine

## 11.1 Recovery classifies the recovered tail before finalizing resume state
After cleanup, the loader determines whether the prior session ended:
- normally
- with a prompt that never received any response
- in the middle of a turn

### Rewrite requirement
Preserve explicit interruption classification as part of recovery.

---

## 11.2 The last relevant message ignores system/progress noise and synthetic API error assistants
Interruption detection computes the last turn-relevant message by skipping bookkeeping messages and certain synthetic API-error assistant entries.

### Rewrite requirement
Preserve “last relevant message” semantics for interruption classification.

---

## 11.3 A trailing assistant usually means the turn completed
After unresolved tool-use cleanup, an assistant as the final relevant message is generally treated as a completed turn.

### Rewrite requirement
Preserve assistant-tail-as-complete semantics.

---

## 11.4 A trailing ordinary user prompt means interrupted prompt
If the last relevant message is a plain non-meta user prompt, the assistant never started responding.

### Rewrite requirement
Preserve interrupted-prompt detection.

---

## 11.5 A trailing tool-result user message usually means interrupted turn, except for terminal-tool cases
A user tool-result tail usually indicates interruption in the middle of a turn, but some tools legitimately terminate the turn without trailing assistant text.

### Rewrite requirement
Preserve terminal-tool exceptions in interruption detection.

---

## 11.6 Attachment tails are treated as interrupted turns
Attachments are part of user-provided turn context; if the transcript ends there, the turn is treated as interrupted.

### Rewrite requirement
Preserve attachment-tail interruption semantics.

---

## 12. Interrupted-turn normalization semantics

## 12.1 Interrupted turns are transformed into synthetic continuation prompts
If the loader detects an interrupted turn rather than an interrupted prompt, it appends a synthetic meta user message equivalent to:

```text
Continue from where you left off.
```

### Rewrite requirement
Preserve interrupted-turn → synthetic continuation conversion.
The exact user-visible wording of the synthetic continuation message does not need to be byte-identical unless another component explicitly depends on exact text matching; an equivalent continuation prompt is sufficient.

---

## 12.2 Public resume state exposes this as interrupted prompt
Even though interruption was internally detected as “mid-turn”, the external/public recovery result exposes it as an interrupted prompt carrying the synthetic continuation message.

### Rewrite requirement
Preserve normalized public interruption state shape.

---

## 13. API-valid transcript stabilization semantics

## 13.1 If the final relevant message is user, recovery inserts a synthetic assistant sentinel
After interruption handling, if the last relevant message is still a user message, a synthetic assistant sentinel is inserted so the transcript remains API-valid even if no immediate continuation happens.

### Rewrite requirement
Preserve trailing-user assistant-sentinel insertion.

---

## 13.2 The sentinel is inserted immediately after the final relevant user message, not just appended blindly at file end
The insertion point matters because later interruption-removal or splice logic expects the assistant sentinel to be paired directly with the relevant trailing user message.

### Rewrite requirement
Preserve correct sentinel placement relative to the final user message.

---

## 14. Process-state restoration from transcript contents

## 14.1 Skill invocation state is restored from transcript attachments before deserialization completes
The loader restores invoked-skill process state from persisted attachments so later compaction cycles and resume behavior stay consistent.

### Rewrite requirement
Preserve transcript-driven process-state restoration for invoked skills.

---

## 14.2 Skill-listing “already announced” latches are restored from attachments
If the transcript already contains a skill-listing attachment, the process suppresses redundant re-announcement on resume.

### Rewrite requirement
Preserve transcript-driven restoration of announcement latches.

---

## 15. Resume hooks and final output assembly

## 15.1 Recovery appends session-start hook output after transcript deserialization
After the transcript has been recovered and deserialized, resume-specific session-start hook messages are appended to the in-memory conversation.

### Rewrite requirement
Preserve post-recovery session-start hook append semantics.

---

## 15.2 The final resume result carries both messages and recovered sidecar metadata
The final return value includes not only the recovered message list, but also associated sidecar/metadata state such as:
- file-history snapshots
- attribution snapshots
- content replacements
- context-collapse commits/snapshot
- agent/session metadata
- worktree state
- PR linkage metadata

### Rewrite requirement
Preserve combined conversation-plus-sidecar recovery output.

---

## 16. Minimal interfaces for a rewrite

A compatible rewrite should expose behavior roughly like:

```ts
type TurnInterruptionState =
  | { kind: 'none' }
  | { kind: 'interrupted_prompt'; message: Message }

type ResumeLoadResult = {
  messages: Message[]
  turnInterruptionState: TurnInterruptionState
  fileHistorySnapshots?: FileHistorySnapshot[]
  attributionSnapshots?: AttributionSnapshotMessage[]
  contentReplacements?: ContentReplacementRecord[]
  contextCollapseCommits?: ContextCollapseCommitEntry[]
  contextCollapseSnapshot?: ContextCollapseSnapshotEntry
  sessionId?: string
}

type ConversationRecovery = {
  loadConversationForResume(
    source: string | LogOption | undefined,
    sourceJsonlFile?: string,
  ): Promise<ResumeLoadResult | null>

  deserializeMessagesWithInterruptDetection(
    serializedMessages: Message[],
  ): {
    messages: Message[]
    turnInterruptionState: TurnInterruptionState
  }

  buildConversationChain(
    messages: Map<string, TranscriptMessage>,
    leaf: TranscriptMessage,
  ): TranscriptMessage[]
}
```

Exact names may vary. The semantics should remain close.

---

## 17. Critical invariants for a rewrite

## 17.1 Resume must reconstruct the effective conversation branch, not replay raw transcript order
Failure mode:
- wrong branch or excess historical context is resumed

## 17.2 Repair passes must run before final chain use when compaction/snip metadata requires them
Failure mode:
- preserved kept messages disappear or removed spans reappear

## 17.3 Recovery must repair parallel tool-use orphaning beyond simple parent traversal
Failure mode:
- sibling tool results vanish from resumed context

## 17.4 Cleanup must remove unresolved tool uses, orphaned thinking, and whitespace assistants
Failure mode:
- resumed transcript is API-invalid

## 17.5 Interrupted turns must normalize to a synthetic continuation prompt
Failure mode:
- resumed execution starts from the wrong semantic place

## 17.6 A trailing user message must be stabilized with an assistant sentinel
Failure mode:
- transcript shape is invalid for downstream API processing

## 17.7 Resume must restore transcript-derived process latches/state such as invoked skills
Failure mode:
- later compaction/resume cycles drift from original behavior

## 17.8 Resume must preserve sidecar metadata alongside the recovered conversation
Failure mode:
- worktree/file-history/replacement/collapse state silently disappears

---

## 18. Relationship to the broader compaction doc

If `docs/session-compaction-and-recovery.md` answers:
- how does the system *write* compacted conversation state?
- how do boundaries, summaries, snips, and preserved segments affect future recovery?

Then this document answers:
- given the persisted state, how does the system *recover* the effective conversation to resume from?

So the documents are intentionally complementary:
- `session-compaction-and-recovery.md` = write+read state machine
- `conversation-recovery-state-machine.md` = read/resume state machine only

---

## 19. Confidence and limits

High confidence:
- source resolution, chain walk, cleanup filters, interruption detection, synthetic continuation insertion, assistant sentinel insertion, and transcript-driven skill state restoration are directly grounded in inspected code

Lower confidence:
- this document intentionally abstracts away some storage optimizations and cross-feature interactions that are covered in the broader compaction/transcript docs

That is deliberate: this file is meant to stay balanced by being narrow and loader-centric rather than duplicating the full compaction write-path documentation.