# Tool-result budgeting and deduplication for a clean-room rewrite

This document captures the budgeting, truncation, deduplication, summarization, and transcript-shaping behavior applied to tool results before they are fed back into the model or persisted as turn state.

It is intended as a behavioral compatibility spec for a clean-room rewrite.

Companion docs:
- `docs/tool-contracts.md`
- `docs/interfaces-and-endpoints.md`
- `docs/message-normalization-for-api.md`
- `docs/turn-failure-and-retry-state-machine.md`
- `docs/path-and-filesystem-safety.md`

Primary inspected sources for this pass:
- `src/query.ts`
- `src/tools.ts`
- `src/Tool.ts`
- `src/utils/getToolName.ts`
- `src/utils/sideQuestion.ts`
- `src/utils/streamingToolUse.ts`
- `src/services/tools/StreamingToolExecutor.ts`
- `src/services/toolResults/toolResultSummaries.ts`
- `src/services/toolResults/dedupToolResults.ts`
- `src/services/toolResults/formatToolResultForAPI.ts`
- `src/services/toolResults/limitToolResultForAPI.ts`
- `src/services/toolResults/toolResultBudget.ts`

---

## 1. Scope

This document is about what happens **after a tool executes but before its result is reintroduced into the model conversation**.

It focuses on:
- per-result output limiting
- aggregate tool-result budgeting
- deduplication across repeated tool outputs
- optional summarization / compaction of tool output
- transcript and API message shape constraints for tool results
- behavior differences between user-visible output and model-fed output

It is not primarily about:
- permissioning
- shell sandboxing
- filesystem safety
- remote API endpoints

---

## 2. Core design principle

Tool outputs are not passed through verbatim as an unbounded append-only stream.

Instead, the runtime treats tool results as a scarce context resource and applies multiple layers of control:
- local truncation/limiting at the individual tool-result level
- formatting into a normalized API-safe structure
- deduplication of semantically repeated tool results
- optional summary generation for repeated or verbose outputs
- aggregate budget enforcement across a turn

### Rewrite requirement
Preserve tool-result handling as a **budgeted normalization pipeline**, not just `tool.execute() -> stringify() -> append`.

---

## 3. Canonical pipeline shape

A compatible rewrite should conceptually behave like:

```ts
for (const rawResult of executedToolResults) {
  const normalized = normalizeToolResult(rawResult)
  const limited = limitToolResult(normalized, perResultPolicy)
  const formatted = formatToolResultForAPI(limited)
  const deduped = maybeDeduplicate(formatted, priorToolResults)
  const budgeted = applyAggregateBudget(deduped, runningBudget)
  const finalResult = maybeSummarizeOrReplace(budgeted)
  appendToolResult(finalResult)
}
```

The real implementation interleaves some of these concerns and treats streaming/non-streaming tool execution slightly differently, but the rewrite should preserve the resulting semantics.

---

## 4. Why this behavior matters

Without this pipeline, a rewrite will regress in at least four ways:
- repeated reads/searches/shell outputs will balloon prompt size and trigger avoidable compaction or overflow
- identical or near-identical tool results will be re-fed pointlessly to the model
- model-visible tool_result messages will drift from the expected content shape
- streaming execution and retry/fallback paths will accumulate stale or duplicate tool results

### Rewrite requirement
Preserve tool-result budgeting and dedup as correctness behavior, not merely performance tuning.

---

## 5. Normalized tool-result shape

## 5.1 Tool results are normalized into API-facing content blocks
The runtime does not rely on arbitrary tool-native return values directly. Tool results are normalized into structured content blocks suitable for assistant/user/tool transcript layers.

At a high level, a tool result associated with a `tool_use_id` becomes a `tool_result` content block with:
- `tool_use_id`
- a normalized content payload
- error/metadata markers when applicable

### Rewrite requirement
Preserve a single normalized model-facing tool-result representation regardless of the internal tool implementation language or return type.

---

## 5.2 Tool result formatting is distinct from tool execution
A tool’s internal return object is not itself the API contract.

The runtime has a formatting stage that decides what parts become:
- plain text content
- structured content fragments
- error flags
- metadata-like annotations

### Rewrite requirement
Preserve a separate formatting layer between raw tool return values and conversation content blocks.

---

## 5.3 Tool-result content must remain valid even on synthetic/error paths
Synthetic tool results are emitted for:
- aborts
- fallback retries
- thrown exceptions after tool_use emission

These synthetic results still conform to the same `tool_result` envelope shape.

### Rewrite requirement
Preserve a single envelope format for both real and synthetic tool results.

---

## 6. Per-result limiting behavior

## 6.1 Individual tool results are constrained before aggregate budgeting
The runtime first limits or truncates individual results before considering overall turn budget.

This avoids one giant result monopolizing the entire tool-result allowance.

### Rewrite requirement
Preserve per-result limiting before aggregate budgeting.

---

## 6.2 Limiting is content-aware, not only byte slicing
The limiting layer is not just “take first N characters”. It is aware of tool-result structure and preserves a coherent API-safe result shape.

Depending on result shape, limiting may preserve:
- prefixes/headers
- structured boundaries
- explanatory truncation markers
- error semantics

### Rewrite requirement
Preserve structure-aware limiting rather than naive string clipping.

---

## 6.3 Truncated results remain self-describing
When a tool result is shortened, the resulting content still signals truncation/omission rather than pretending to be complete.

### Rewrite requirement
Preserve explicit truncation signaling in limited tool results.

---

## 6.4 Limiting must preserve essential identity fields
Even when content is shortened, fields needed for conversation integrity remain intact, especially:
- `tool_use_id`
- error-vs-success semantics
- any content framing needed by downstream normalization

### Rewrite requirement
Never truncate away the identifiers and flags required to match a result back to its originating tool use.

---

## 7. Aggregate tool-result budgeting

## 7.1 The runtime tracks a cumulative budget across tool results in a turn
Budgeting is not only per-result. The runtime also tracks the total amount of tool result material being fed back into the model for the turn/iteration.

### Rewrite requirement
Preserve aggregate budget tracking across the set of tool results returned in a continuation cycle.

---

## 7.2 Aggregate budget is applied after normalization/limiting
The budget decision is made on the normalized/limited representation that will actually be appended, not only on raw source payload size.

### Rewrite requirement
Budget against the model-visible representation, not the raw native tool payload alone.

---

## 7.3 Over-budget results may be summarized or replaced rather than appended verbatim
If the cumulative budget is at risk, the runtime can prefer shortened/summarized representations over full repeated payloads.

### Rewrite requirement
Preserve substitution of compact representations when aggregate budget pressure is high.

---

## 7.4 Budgeting is a context-protection mechanism, not just UI trimming
The primary reason for budget enforcement is to protect subsequent model turns from being dominated by tool output.

### Rewrite requirement
Design budgeting policy around model context preservation, not just terminal readability.

---

## 8. Deduplication semantics

## 8.1 Deduplication is based on repeated tool-result content, not just repeated tool names
The runtime does not merely say “consecutive bash calls are duplicates.” It reasons over the output/result payload and whether feeding it again adds value.

### Rewrite requirement
Preserve content-based deduplication rather than only tool-name-based suppression.

---

## 8.2 Deduplication compares against prior tool outputs in the relevant turn context
A result may be recognized as redundant because it repeats information already supplied by earlier tool results in the same query progression.

### Rewrite requirement
Preserve comparison against relevant prior tool results, not just the immediately previous one if the original behavior spans more than that.

---

## 8.3 Deduplicated results are not silently dropped without replacement semantics
If a result is deduplicated away from the verbose form, the conversation still needs a coherent continuation shape. The runtime may replace the payload with a compact note/summary rather than omitting the tool_result entirely.

This matters because `tool_use` / `tool_result` closure must still hold.

### Rewrite requirement
Preserve closure of every `tool_use` with some corresponding `tool_result`, even when the payload is deduplicated.

---

## 8.4 Deduplication is especially important for read/search/list-style tools
Tools that often return repeated or overlapping textual payloads are the major budget risk, such as:
- file reads
- search/grep/glob outputs
- shell commands that repeat prior state
- LSP/search-like inspection results

### Rewrite requirement
Prioritize robust dedup behavior for high-repetition inspection tools.

---

## 9. Summary generation for tool results

## 9.1 Tool-result summaries are generated asynchronously in some flows
The runtime can create a pending tool-use summary promise, meaning summary generation is not always fully synchronous with raw tool execution.

### Rewrite requirement
Preserve the ability to decouple summary creation from the immediate tool execution path.

---

## 9.2 Summaries are model/context-facing compression artifacts
A summary is not merely a UI note. It is a compact representation intended to reduce future context cost while retaining salient information.

### Rewrite requirement
Preserve summaries as semantic replacements for verbose tool outputs, not just cosmetic annotations.

---

## 9.3 Summary generation must not violate tool-use closure invariants
Even when a summary exists, the transcript shape still needs a valid result for each tool use.

### Rewrite requirement
Preserve summary insertion as a payload transformation, not as deletion of the `tool_result` envelope.

---

## 10. Streaming tool execution interaction

## 10.1 Streaming execution has the same budgeting invariants as non-streaming execution
Whether tool results are produced through a streaming executor or a more ordinary batch flow, the final model-visible result must still obey limiting, dedup, and closure rules.

### Rewrite requirement
Preserve identical result-shape invariants across streaming and non-streaming tool execution modes.

---

## 10.2 Streaming executor state must not leak stale results across retries/fallbacks
If a streaming attempt is abandoned:
- queued/completed results from the abandoned executor are discarded
- a new executor instance is created
- only results belonging to the surviving attempt may enter the transcript/model state

### Rewrite requirement
Preserve attempt-local ownership of streaming tool results.

---

## 10.3 Abort repair results still participate in the same formatting/shape invariants
When an abort drains pending tool executions into synthetic `tool_result` errors, the result still has to be valid in the same normalized envelope.

### Rewrite requirement
Preserve unified formatting rules for executor-produced and abort-repair-produced tool results.

---

## 11. Transcript versus model-input concerns

## 11.1 Model-fed tool results and user-visible tool logs are not identical concerns
The runtime distinguishes between what is shown to the user during execution and what is serialized back into conversation history for the next model call.

### Rewrite requirement
Preserve separation between execution telemetry/UI output and the compact model-facing tool_result representation.

---

## 11.2 The budgeted representation is the one that matters for continuation
The key compatibility behavior is what gets appended to `messagesForQuery` / conversation state for the next model round, not necessarily every byte of local tool stdout.

### Rewrite requirement
Treat the model-fed representation as the compatibility surface.

---

## 12. Side-question and helper-query considerations

## 12.1 Small helper/side-question flows still need disciplined tool-result shaping
Even helper flows can become expensive if they repeatedly feed verbose inspection output back into the model.

### Rewrite requirement
Preserve tool-result budgeting behavior across helper query classes, not just the main chat turn.

---

## 12.2 Deduplication reduces repeated helper-context churn
Where helper queries repeatedly inspect the same state, deduplication prevents the model context from being repopulated with the same evidence over and over.

### Rewrite requirement
Preserve dedup as a cross-cutting context-protection mechanism, not a main-turn-only optimization.

---

## 13. Interaction with turn failure/retry logic

## 13.1 Tool-result closure is required before fallback retry
If fallback triggers after tool_use emission, synthetic error tool_results are emitted before retrying. These repaired results still count as the closure mechanism for those tool uses.

### Rewrite requirement
Preserve tool-result closure before abandoning an attempt.

---

## 13.2 A rewrite must not duplicate successful tool results across retries
If an attempt is retried due to fallback or stream abandonment, successful tool results from the abandoned attempt must not be replayed into the surviving attempt unless they are intentionally re-executed and re-associated.

### Rewrite requirement
Preserve retry isolation for tool-result ownership.

---

## 13.3 Deduplication must not accidentally merge results from distinct tool_use IDs
Two results with similar content may still correspond to distinct tool_use actions. Dedup can compress payloads, but it must not collapse identity or lose one result envelope entirely.

### Rewrite requirement
Preserve per-tool_use identity even when payload content is deduplicated.

---

## 14. Clean-room interface guidance

A rewrite should expose interfaces roughly like:

```ts
interface ToolResultFormatter {
  format(raw: RawToolResult, ctx: FormatContext): FormattedToolResult
}

interface ToolResultLimiter {
  limit(result: FormattedToolResult, policy: PerResultPolicy): FormattedToolResult
}

interface ToolResultDeduplicator {
  deduplicate(
    result: FormattedToolResult,
    prior: FormattedToolResult[],
  ): FormattedToolResult
}

interface ToolResultBudgeter {
  apply(
    result: FormattedToolResult,
    state: ToolResultBudgetState,
  ): FormattedToolResult
}

interface ToolResultSummarizer {
  summarize(results: FormattedToolResult[]): Promise<ToolResultSummary | null>
}
```

And a conversation-facing envelope shape roughly like:

```ts
type ToolResultBlock = {
  type: 'tool_result'
  tool_use_id: string
  is_error?: boolean
  content: ToolResultContent
}
```

Exact internals can vary, but these concerns should remain separable.

---

## 15. Critical invariants to preserve

## 15.1 Every tool_use must still produce a tool_result envelope
Even if content is deduplicated, summarized, truncated, or synthetic.

Failure mode:
- invalid conversation/tool trajectory

## 15.2 Deduplication must compress payload, not erase identity
Failure mode:
- transcript no longer faithfully reflects tool execution structure

## 15.3 Aggregate budgeting must protect subsequent model turns from tool-output domination
Failure mode:
- avoidable prompt-too-long and compaction churn

## 15.4 Per-result limiting must happen before aggregate reasoning
Failure mode:
- one oversized payload crowds out all others

## 15.5 Formatting must be centralized, not reimplemented ad hoc per tool
Failure mode:
- inconsistent API shapes and retry/abort edge-case corruption

## 15.6 Retry/fallback paths must discard stale executor-owned tool results
Failure mode:
- stale tool_result blocks referencing abandoned attempts or obsolete tool_use IDs

## 15.7 Summaries must behave as semantic compression, not lossy identity deletion
Failure mode:
- model loses that a tool completed or which tool_use the result belongs to

---

## 16. Suggested continuation docs priority

After this doc, the best adjacent follow-up is:
- `docs/model-and-request-shaping.md`

Reason:
- together, these two docs would cover both sides of the context-economy boundary:
  - how tool outputs are compressed before entering the conversation
  - how the final request is shaped before reaching the model API

---

## 17. Confidence and limits

High confidence:
- existence of dedicated tool-result formatting, limiting, deduplication, budget, and summary layers; the use of pending tool-use summaries; and the requirement that tool_result envelopes remain valid across retry/abort/fallback paths are directly supported by the inspected code layout and surrounding query-loop behavior

Moderate confidence:
- some of the exact heuristics used inside the budgeting/dedup layers are summarized at the semantic level here rather than reproduced line-by-line, because this document is intended to preserve externally relevant behavior for a clean-room rewrite rather than copy implementation constants verbatim
