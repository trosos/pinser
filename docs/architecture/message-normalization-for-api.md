# Message normalization for API for a clean-room rewrite

This document describes the transformation layer that turns persisted/runtime messages into API-safe request messages. It focuses on behavioral contracts rather than source-level implementation details.

This layer is critical because many invariants are enforced **only** here. A rewrite that preserves tools, permissions, persistence, and UI behavior can still fail in production if it sends malformed message sequences to the model API.

Companion docs:
- `docs/transcript-and-persistence-semantics.md`
- `docs/tool-contracts.md`
- `docs/interfaces-and-endpoints.md`
- `docs/implementation-notes-and-gotchas.md`

Primary inspected sources for this pass:
- `src/utils/messages.ts`
- `src/utils/conversationRecovery.ts`

---

## 1. Purpose

The runtime maintains a richer message model than what can be sent to the API.

Before each model request, messages are normalized to satisfy backend constraints around:
- role alternation
- valid content-block ordering
- tool-use / tool-result pairing
- attachment placement
- unsupported block/field stripping
- empty/whitespace assistant content
- trailing thinking blocks
- legacy or stale persisted fields

A clean-room rewrite should treat this as a dedicated subsystem:

```ts
type MessagePreparationPipeline = {
  normalizeForResume(logMessages: PersistedMessage[]): RuntimeMessage[]
  normalizeForApi(runtimeMessages: RuntimeMessage[], tools: Tool[]): ApiMessage[]
  ensureToolResultPairing(messages: ApiMessage[]): ApiMessage[]
}
```

The exact names can vary. The existence of a distinct normalization pipeline should not.

---

## 2. Conceptual message strata

A rewrite should preserve three conceptual message layers.

## 2.1 Persisted/runtime messages
These include more than just API-visible turns:
- `user`
- `assistant`
- `attachment`
- `system`
- `progress`
- some synthetic or bookkeeping messages

## 2.2 Resume-normalized messages
Resume loading repairs or drops malformed state from interrupted/legacy sessions.
This includes filtering:
- unresolved tool uses
- orphaned thinking-only assistant fragments
- whitespace-only assistant fragments

It may also append synthetic continuation/sentinel messages.

## 2.3 API-normalized messages
The final API payload is a strict projection containing only alternating user/assistant turns with legal content block shapes.

### Rewrite requirement
Preserve a multi-stage transformation pipeline rather than treating persistence format and API format as the same thing.

---

## 3. Input and output shapes

## 3.1 Runtime input shape
Conceptually:

```ts
type RuntimeMessage =
  | UserMessage
  | AssistantMessage
  | AttachmentMessage
  | ProgressMessage
  | SystemMessage
```

## 3.2 API output shape
Conceptually:

```ts
type ApiMessage = UserMessage | AssistantMessage
```

Additional constraints on the API form:
- only user and assistant roles remain
- system messages are either removed or converted into user content where allowed
- progress messages never remain
- attachment messages are lowered into user content blocks
- consecutive user turns are merged
- some consecutive assistant fragments are merged

### Rewrite requirement
Preserve a final API payload consisting only of legal user/assistant messages.

---

## 4. High-level API normalization pipeline

A compatible rewrite should perform an equivalent sequence roughly like:

1. reorder attachment-bearing messages for API compatibility
2. drop virtual/display-only messages
3. identify synthetic API error messages and mark related earlier user content for stripping
4. filter out non-API-visible message classes
5. convert local-command system messages into user messages
6. normalize user messages
   - strip unavailable or unsupported tool-reference blocks
   - strip previously failed large attachment/document/image blocks from affected meta messages
   - maybe inject a turn-boundary text sibling for tool-reference content
   - merge adjacent user messages
7. normalize assistant messages
   - canonicalize tool names
   - normalize tool inputs for API
   - strip unsupported tool-use fields when required
   - merge assistant fragments with the same API message id
8. lower attachment messages into user messages and merge them
9. optionally relocate tool-reference sibling text off problematic messages
10. filter orphaned thinking-only assistant messages
11. strip trailing thinking from the final assistant message
12. filter whitespace-only assistant messages
13. ensure non-final assistant messages have non-empty content
14. optionally merge adjacent users again for post-pass cleanup
15. sanitize error tool_result content
16. append message-id tags for snip-like features if enabled
17. validate images for API limits
18. ensure tool-result pairing defensively

The exact pass ordering can vary slightly, but several order dependencies are important and should be preserved.

---

## 5. Role-level transformations

## 5.1 Progress messages are excluded from API payloads
`progress` messages are runtime/UI-only and must never be sent to the model API.

### Rewrite requirement
Filter all progress messages before API submission.

---

## 5.2 Most system messages are excluded from API payloads
System messages generally represent bookkeeping, display, or local state and are not sent to the model.

### Exception: local command output system messages
A specific class of system message representing local command output is converted into a user message so the model can reference earlier command output in later turns.

### Rewrite requirement
Preserve:
- broad exclusion of system messages from API payloads
- explicit lowering of local-command output system messages into user messages

---

## 5.3 Attachment messages are lowered into user content
Attachment messages do not survive as their own top-level API role. They become one or more user messages/content blocks.

### Rewrite requirement
Preserve attachment lowering into user-side content blocks before API send.

---

## 5.4 Virtual messages are display-only
Some user/assistant messages are flagged as virtual/display-only and must never reach the API.

### Rewrite requirement
Filter virtual messages before API submission.

---

## 6. User-message normalization semantics

## 6.1 Consecutive user messages are merged
The normalization layer merges adjacent user messages into a single user turn.

Why this matters:
- some backends do not accept repeated user roles
- runtime flows naturally produce adjacent user turns via attachments, tool results, local command lowering, interruption recovery, and queued prompts

### Rewrite requirement
Preserve adjacent-user merging in API preparation.

---

## 6.2 Merge preserves non-meta UUID identity for stable downstream tags
When merging a meta user message with a non-meta user message, the resulting merged message preserves the non-meta message UUID where needed.

Reason:
- downstream message-ID tags are derived from UUIDs
- meta messages may receive fresh UUIDs frequently
- changing the preserved UUID destabilizes message tags across API calls

### Rewrite requirement
Preserve stable surviving user identity when merging meta and non-meta messages.

---

## 6.3 Text-text seams need a separator
When two user messages are merged and the boundary is text-to-text, a newline is inserted at the seam.

Reason:
- adjacent text blocks can otherwise concatenate into a semantically incorrect string
- example: `"2 + 2"` and `"3 + 3"` must not become `"2 + 23 + 3"`

### Rewrite requirement
Preserve explicit seam separation for text-to-text user merges.

---

## 6.4 Tool results must be hoisted before sibling user content
Inside a single merged user message, `tool_result` blocks must come before non-tool-result blocks.

Reason:
- the API expects tool results to immediately follow the relevant tool-use context structurally
- later text/attachment siblings after a tool result can produce invalid or brittle wire representations

### Rewrite requirement
Preserve hoisting of `tool_result` blocks to the front of the merged user content array.

---

## 6.5 User-content merging may fold siblings into trailing tool_result content
If a user message ends with a `tool_result`, and later sibling blocks would otherwise follow it, the system may fold those sibling blocks into the tool_result’s own content instead of leaving them as siblings.

This behavior exists to avoid pathological wire renderings that can teach the model an unwanted turn boundary pattern.

### Rewrite requirement
Preserve a mechanism that prefers embedding compatible sibling content into trailing tool results rather than always leaving it as a new sibling block.

---

## 6.6 Folding into tool_result has type constraints
Not every sibling block can be folded into a tool result arbitrarily.

Observed rules:
- text blocks can be folded
- some other content blocks such as image/document/search-result may be foldable in newer behavior
- `tool_reference` content imposes special constraints and may force fallback to sibling form
- `is_error` tool_results may accept only text content, so non-text siblings must be excluded from folding there

### Rewrite requirement
Preserve tool-result-content-type validation when folding sibling content into an existing tool result.

---

## 6.7 Empty string-like tool-result content should not be relied on
The system is generally biased toward ensuring content visible to the model is non-empty or structurally meaningful.

### Rewrite requirement
Do not emit structurally empty or semantically blank user/tool-result content where the original system substitutes a marker or repaired content.

---

## 7. Tool-reference and tool-search normalization

## 7.1 Tool-reference blocks are conditional on tool-search capability
When tool-search is not enabled, tool-reference blocks are stripped from user messages.

When tool-search is enabled, tool-reference blocks for unavailable/disconnected tools are stripped selectively.

### Rewrite requirement
Preserve capability-aware stripping of tool-reference blocks.

---

## 7.2 Unavailable tools are stripped by current available tool set
The API preparation pass compares tool references against the current available tool names and removes references that no longer point to a live tool.

### Rewrite requirement
Preserve normalization against the current tool registry, not just persisted transcript content.

---

## 7.3 Tool-reference messages may need explicit turn-boundary text siblings
When tool-reference content appears at the prompt tail, the system may inject a small sibling text block to create a cleaner turn boundary on the wire.

This is done only in API prep, not stored in the transcript.

### Rewrite requirement
Preserve the ability to add ephemeral API-only boundary text around tool-reference payloads to avoid backend/model stop-sequence pathologies.

---

## 7.4 Later passes may relocate those siblings instead of injecting them
A later API-preparation mode can relocate text siblings away from tool-reference-bearing messages rather than injecting them directly.

### Rewrite requirement
Preserve the semantic intent: avoid problematic tool-reference-tail boundary patterns, whether by injection or relocation.

---

## 8. Synthetic API error cleanup

## 8.1 Some synthetic API error assistant messages are not themselves sent back
Synthetic API error messages are used to infer cleanup actions, then are removed from the outgoing transcript.

### Rewrite requirement
Preserve synthetic-error-driven cleanup without including those synthetic error messages in the final API request.

---

## 8.2 Prior problematic attachment blocks are stripped from the triggering meta user message
If a previous meta user message contained an oversized/invalid image or document that caused an API error, later normalization strips the offending block type from that specific prior user message to avoid re-sending the same bad payload forever.

### Rewrite requirement
Preserve targeted stripping of previously rejected media/document blocks from the specific prior user message that triggered the error.

This is a very important self-healing behavior.

---

## 8.3 If stripping removes all content, that user message is dropped
If the targeted removal empties the affected meta message entirely, normalization skips that message.

### Rewrite requirement
Preserve drop-if-empty behavior after targeted block stripping.

---

## 9. Assistant-message normalization semantics

## 9.1 Assistant fragments with the same API message id are merged
Streaming can emit multiple assistant fragments that belong to the same logical API response. These are merged when they share the same assistant message id.

### Rewrite requirement
Preserve same-message-id assistant fragment merging.

---

## 9.2 Merge walk skips over tool-result user messages when searching backward
When searching for a prior assistant fragment to merge with, the logic can skip over intervening tool-result user messages and irrelevant noise.

### Rewrite requirement
Preserve backward-merge logic that tolerates interleaved tool-result user messages.

---

## 9.3 Tool names are canonicalized against the live tool registry
Assistant `tool_use` blocks may contain legacy/alias names. During API prep, tool names are normalized to the canonical current tool name if the tool exists.

### Rewrite requirement
Preserve canonical tool-name rewriting via the live tool registry.

---

## 9.4 Tool inputs are normalized before API send
Assistant `tool_use` input objects are normalized per tool before submission.

Examples include stripping fields that are runtime-only or not accepted by the public API shape.

### Rewrite requirement
Preserve per-tool API input normalization.

---

## 9.5 Unsupported fields like `caller` are stripped when tool-search is disabled
Some stored tool-use blocks may include fields only legal under optional beta/tool-search modes. If that mode is not active, those fields are stripped before submission.

### Rewrite requirement
Preserve capability-aware field stripping from assistant tool_use blocks.

---

## 9.6 Trailing thinking blocks on the final assistant message must be removed
The API does not accept an assistant message ending with thinking/redacted-thinking blocks.

Behavior:
- if the final assistant message ends with one or more thinking blocks, they are removed
- if all blocks were thinking, a placeholder text block is inserted instead

### Rewrite requirement
Preserve trailing-thinking removal on the final assistant message, including placeholder insertion if nothing remains.

---

## 9.7 Orphaned thinking-only assistant messages are removed earlier
If an assistant message consists only of thinking blocks and there is no sibling assistant fragment with the same message id containing real content, it is removed as orphaned.

### Rewrite requirement
Preserve orphaned-thinking-only filtering before final API send.

---

## 9.8 Whitespace-only assistant messages are removed
Assistant messages whose content consists only of whitespace text blocks are removed entirely.

If this creates adjacent user messages, they are merged.

### Rewrite requirement
Preserve whitespace-only assistant filtering and follow-up user merging.

---

## 9.9 Non-final assistant messages with empty content get placeholders
The API allows an optional final empty assistant message for prefill-like semantics, but non-final assistant messages must not have empty content arrays.

Behavior:
- non-final empty assistant → replace with placeholder text block
- final empty assistant → allowed to remain empty

### Rewrite requirement
Preserve this exact distinction between non-final and final empty assistant messages.

---

## 10. Tool-use / tool-result pairing semantics

## 10.1 Pairing is validated defensively before API submission
Even after resume-time recovery, the API-prep stage performs a final tool-use/tool-result pairing pass.

### Rewrite requirement
Preserve final defensive validation of tool-use/tool-result pairing before sending to the API.

---

## 10.2 Forward repair: missing tool_result may be synthesized
If a `tool_use` has no matching `tool_result`, the system can synthesize a placeholder error tool_result.

### Rewrite requirement
Preserve forward repair capability for missing tool results, unless strict mode is active.

---

## 10.3 Reverse repair: orphaned tool_result blocks are stripped
If a `tool_result` references a nonexistent tool_use, it is stripped from the outgoing message sequence.

This includes cases where the transcript begins mid-turn with a tool result whose originating assistant was compacted or removed.

### Rewrite requirement
Preserve stripping of orphaned tool results.

---

## 10.4 Duplicate tool_use IDs across the whole outgoing transcript are invalid
The pairing/validation pass tracks tool_use IDs globally across the outgoing message list and treats duplicates as repair-worthy or fatal.

### Rewrite requirement
Preserve transcript-wide uniqueness enforcement for tool_use IDs.

---

## 10.5 Strict pairing mode must exist
For some flows, synthetic repair is not acceptable because it would contaminate downstream evaluation/training data.

### Rewrite requirement
Preserve a strict mode in which pairing mismatches throw/fail rather than being repaired.

---

## 10.6 Synthetic placeholder content must be distinguishable
When synthetic tool results are inserted, their content is a recognizable internal placeholder rather than pretending to be real tool output.

### Rewrite requirement
Preserve a clearly synthetic placeholder marker for repaired tool results.

---

## 11. Attachment normalization semantics

## 11.1 Attachments are reordered before API lowering
Attachments are first reordered relative to nearby messages to ensure better API compatibility before they are lowered into user messages.

### Rewrite requirement
Preserve attachment reordering as a pre-lowering pass.

---

## 11.2 Attachment lowering may emit multiple user messages
A single attachment artifact may normalize into one or more user-form messages/content blocks.

### Rewrite requirement
Do not assume one attachment always maps to exactly one user message.

---

## 11.3 Some attachment-derived messages are wrapped with reminder text conditionally
Certain modes wrap attachment-derived messages in a system-reminder-like text wrapper before later merge/smoosh passes.

### Rewrite requirement
Preserve support for attachment-originated reminder wrapping where the runtime mode expects it.

---

## 12. Ordering dependencies between passes

Some normalization passes are explicitly order-sensitive.
A rewrite should preserve these dependencies even if the internal implementation changes.

## 12.1 Filter trailing thinking before whitespace-only filtering on the last assistant
If whitespace filtering runs too early, a message like:
- text("\n\n")
- thinking("...")

can survive whitespace filtering because it contains a non-text block, then lose the thinking block later and become invalid whitespace-only text.

### Rewrite requirement
Preserve the order: trailing-thinking cleanup before whitespace-only filtering in the final assistant cleanup path.

---

## 12.2 Merge-adjacent-users may need to run after assistant cleanup too
Some cleanup passes remove assistant messages, which can create new user-user adjacency that must be merged afterward.

### Rewrite requirement
Preserve a post-filter adjacent-user merge opportunity.

---

## 12.3 Message-ID tags must be appended after all merging
Message-ID tags used by history/snip tooling are appended only after merges and structural cleanup so the tags correspond to the final surviving messages.

### Rewrite requirement
Preserve message-tag injection as a late-stage pass.

---

## 12.4 Image validation happens late on the final sanitized payload
Image validation checks the actual outgoing message content after other cleanup/stripping/merging has completed.

### Rewrite requirement
Preserve image validation on the final API-bound payload, not an earlier pre-normalized form.

---

## 13. Resume-time normalization contracts that feed API normalization

Although this doc focuses on the pre-API path, a rewrite should also preserve the earlier resume-time repairs because the API normalization layer depends on them.

## 13.1 Unresolved tool uses are filtered during resume load
Resume load removes assistant messages whose tool_use blocks are all unresolved.

### Rewrite requirement
Preserve unresolved-tool-use filtering at resume time.

---

## 13.2 Invalid persisted permission-mode values are stripped
Persisted fields coming from disk are sanitized before they re-enter runtime logic.

### Rewrite requirement
Preserve read-time sanitization of persisted enum-like values.

---

## 13.3 Interrupted turns are normalized with a synthetic continuation prompt
If the last meaningful persisted state suggests a mid-turn interruption, resume appends a synthetic meta user message asking to continue.

### Rewrite requirement
Preserve continuation-prompt synthesis for interrupted resumes.

---

## 13.4 Trailing user message gets a synthetic assistant sentinel on resume
After resume normalization, if the conversation ends with a user message, a synthetic assistant sentinel is inserted so the transcript is API-valid even before the next real assistant response.

### Rewrite requirement
Preserve synthetic assistant sentinel insertion on resume.

---

## 14. Minimal contract for message operations

A compatible rewrite should expose behaviorally equivalent operations like:

```ts
type MessageNormalizer = {
  normalizeMessages(messages: RuntimeMessage[]): NormalizedMessage[]
  normalizeMessagesForAPI(
    messages: RuntimeMessage[],
    tools: Tool[],
  ): ApiMessage[]

  mergeUserMessages(a: UserMessage, b: UserMessage): UserMessage
  mergeAssistantMessages(a: AssistantMessage, b: AssistantMessage): AssistantMessage
  mergeUserMessagesAndToolResults(a: UserMessage, b: UserMessage): UserMessage

  filterUnresolvedToolUses(messages: RuntimeMessage[]): RuntimeMessage[]
  filterOrphanedThinkingOnlyMessages(messages: RuntimeMessage[]): RuntimeMessage[]
  filterWhitespaceOnlyAssistantMessages(messages: RuntimeMessage[]): RuntimeMessage[]
  stripSignatureBlocks(messages: RuntimeMessage[]): RuntimeMessage[]
  ensureToolResultPairing(messages: ApiMessage[]): ApiMessage[]
}
```

Exact function names may differ; the important part is that these behaviors exist explicitly somewhere.

---

## 15. Critical invariants for a rewrite

## 15.1 Final API payload contains only legal user/assistant turns
Failure mode:
- API rejects progress/system/attachment/virtual messages

## 15.2 Adjacent users are merged
Failure mode:
- backend rejects consecutive user roles or interprets them inconsistently

## 15.3 Tool results are hoisted ahead of sibling content
Failure mode:
- invalid tool-result ordering or wire-shape instability

## 15.4 Assistant fragments with same message id are merged
Failure mode:
- thinking/tool_use/text blocks stay fragmented and later validation breaks

## 15.5 Trailing thinking is removed from final assistant
Failure mode:
- API rejects final assistant content

## 15.6 Whitespace-only and orphaned-thinking assistant fragments are stripped
Failure mode:
- API errors during replay or resume

## 15.7 Tool-use / tool-result pairing is validated at the end
Failure mode:
- unrecoverable bad transcripts after interruptions/compactions

## 15.8 Tool-search-specific fields and blocks are capability-gated
Failure mode:
- sending unsupported fields/blocks when the optional backend feature is off

## 15.9 Previously rejected oversized media/doc content is stripped from the original meta user message
Failure mode:
- every subsequent call resends the same invalid payload forever

## 15.10 UUID/message-tag stability across merges matters
Failure mode:
- prompt-cache churn, unstable history references, or tooling mismatch

---

## 16. What may vary vs what should stay close

## Preserve closely
- role filtering/exclusion semantics
- user-user merge semantics
- assistant same-id merge semantics
- tool-result hoisting
- orphaned-thinking / whitespace-only cleanup
- trailing-thinking cleanup on final assistant
- capability-aware stripping of tool-reference blocks and tool_use fields
- targeted removal of previously rejected attachment/media blocks
- final tool-use/tool-result pairing validation
- late-stage tag injection and final image validation

## Can vary somewhat
- exact helper names and decomposition
- exact placeholder wording for repaired empty content
- exact feature-gating mechanism
- exact implementation of tool-reference sibling relocation vs injection

---

## 17. Confidence and limits

High confidence:
- the main user/assistant merge semantics, tool-result hoisting, assistant cleanup passes, tool-reference/tool-search stripping, and final pairing validation are directly supported by inspected code
- several comments in the code make clear these behaviors are deliberate fixes for concrete production failures

Lower confidence:
- this doc intentionally abstracts over some flag-gated variants and does not enumerate every content-block subtype in the SDK surface
- some helper behavior depends on optional features that were not exhaustively traced through all call sites

Even so, this should be a solid clean-room contract for reimplementing the API-bound message transformation layer.