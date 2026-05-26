# Tool input streaming and partial assembly for a clean-room rewrite

This document captures the behavior around partially streamed tool uses, early tool execution, progress/result ordering, streaming-attempt discard, and the invariants needed so partial assistant/tool state remains coherent.

It is intended as a behavioral compatibility spec for a clean-room rewrite.

Companion docs:
- `docs/tool-contracts.md`
- `docs/tool-result-budgeting-and-dedup.md`
- `docs/turn-failure-and-retry-state-machine.md`
- `docs/model-and-request-shaping.md`
- `docs/message-normalization-for-api.md`

Primary inspected sources for this pass:
- `src/services/tools/StreamingToolExecutor.ts`
- `src/services/tools/toolExecution.ts`
- `src/query.ts`
- `src/utils/api.ts`

---

## 1. Scope

This document is about the **streaming half of the tool I/O path**.

It focuses on:
- request-side enablement of tool input streaming
- early execution of tools as streamed tool uses arrive
- ordering and concurrency rules for streamed tool execution
- progress message emission during tool execution
- partial/abandoned attempt handling
- synthetic tool-result generation when streaming is interrupted or discarded

It is not primarily about:
- individual tool business logic
- permission rule storage
- shell sandboxing
- remote API endpoint taxonomy

---

## 2. Core design principle

The runtime does not wait for an entire assistant turn to fully complete before beginning tool execution.

Instead, when enabled, it overlaps:
- assistant streaming
- tool-use discovery
- tool execution
- progress emission
- final ordered tool-result delivery

This reduces latency, but only works because the runtime maintains strict ownership and ordering rules.

### Rewrite requirement
Preserve streaming tool execution as a coordinated state machine, not as naive “fire tool as soon as bytes arrive” behavior.

---

## 3. End-to-end conceptual pipeline

A compatible rewrite should behave conceptually like:

```ts
while (assistantStreamOpen) {
  const event = await nextStreamEvent()
  updatePartialAssistantState(event)

  if (event.completesToolUseBlock) {
    streamingExecutor.addTool(toolUseBlock, assistantMessage)
  }

  yield anyExecutorProgressImmediately()
  yield anyCompletedToolResultsThatAreNowOrderSafe()
}

yield remainingExecutorResultsInOrder()
```

That is the governing shape even if the concrete event plumbing differs.

---

## 4. Request-side enablement

## 4.1 Fine-grained/eager tool input streaming is explicitly requested, not assumed
The runtime only asks the API for eager/fine-grained tool input streaming by adding a dedicated per-tool schema field when the relevant gates/provider combination allow it.

### Rewrite requirement
Preserve explicit request-side opt-in for tool input streaming.

---

## 4.2 Tool input streaming fields are provider-gated because some providers reject them
The runtime only emits the eager tool-input-streaming field against supported provider/config combinations.

### Rewrite requirement
Preserve provider-aware omission of tool-input-streaming request fields on incompatible providers.

---

## 4.3 Experimental tool-streaming request fields can be stripped centrally
A final schema-shaping choke point can strip experimental fields before transport.

### Rewrite requirement
Preserve a central strip/omit point for non-portable tool-streaming request fields.

---

## 5. Streaming executor responsibilities

A compatible streaming executor owns at least these responsibilities:
- register tool uses as they become executable
- decide whether a tool may start now or must wait
- track per-tool status (`queued`, `executing`, `completed`, `yielded`)
- collect progress and final result messages separately
- maintain attempt-local ownership of tool results
- synthesize error tool_results on discard/abort/error paths
- yield results in a stable order
- expose updated tool-use context after context modifiers

### Rewrite requirement
Preserve a dedicated streaming executor abstraction rather than scattering this logic across the query loop.

---

## 6. Tool lifecycle states

A compatible rewrite should model tool streaming state roughly like:

```ts
type ToolStatus = 'queued' | 'executing' | 'completed' | 'yielded'

type TrackedTool = {
  id: string
  block: ToolUseBlock
  assistantMessage: AssistantMessage
  status: ToolStatus
  isConcurrencySafe: boolean
  pendingProgress: Message[]
  results?: Message[]
  contextModifiers?: Array<(ctx: ToolUseContext) => ToolUseContext>
}
```

### Rewrite requirement
Preserve explicit per-tool lifecycle state rather than inferring everything from promise existence.

---

## 7. Starting execution early

## 7.1 Tools are eligible to enter the executor as soon as a complete tool-use block is available
The system does not need to wait for the whole assistant turn to end before registering a tool use.

### Rewrite requirement
Preserve block-level early execution once tool input is sufficiently assembled and validated.

---

## 7.2 Unknown tools are converted immediately into completed error results
If the streamed tool name does not resolve to a known tool, the executor records a completed synthetic error result instead of leaving the tool use hanging.

### Rewrite requirement
Preserve immediate closure for unknown streamed tools.

---

## 7.3 Tool concurrency safety is determined from parsed input plus tool policy
The executor evaluates whether a tool is concurrency-safe only after parsing the input against the tool schema and consulting the tool’s concurrency policy.

If parsing or policy evaluation fails, it falls back conservatively to non-concurrent behavior.

### Rewrite requirement
Preserve conservative concurrency classification for malformed or uncertain tool inputs.

---

## 8. Concurrency model

## 8.1 Concurrent-safe tools may run alongside other concurrent-safe tools
If every currently executing tool is concurrency-safe, additional concurrency-safe tools may start.

### Rewrite requirement
Preserve explicit concurrency-safe parallelism.

---

## 8.2 Non-concurrent tools require exclusive execution
A non-concurrent tool only starts when no other tool is executing.

### Rewrite requirement
Preserve exclusive execution for non-concurrent tools.

---

## 8.3 Non-concurrent tools also create an ordering barrier in queue processing
When the queue reaches a non-concurrent tool that cannot yet run, the executor stops progressing later queued tools behind it.

This preserves ordering/serialization semantics.

### Rewrite requirement
Preserve queue barriers created by non-concurrent tools.

---

## 9. Progress versus result separation

## 9.1 Progress messages are buffered separately from final tool results
The executor stores progress messages in a separate pending-progress queue per tool and yields them immediately when available.

### Rewrite requirement
Preserve separate handling of progress output versus final tool_result messages.

---

## 9.2 Progress can be yielded before the tool’s final ordered result is eligible
Progress emission is opportunistic and user-facing; final results still obey the executor’s ordering rules.

### Rewrite requirement
Preserve “progress early, result in order” behavior.

---

## 9.3 Completion ordering is distinct from execution completion time
A later tool that completes earlier does not necessarily have its final result yielded first if ordering constraints say otherwise.

### Rewrite requirement
Preserve deterministic result-yield order independent of raw promise completion order.

---

## 10. Ordered result delivery

## 10.1 Completed results are yielded only when their position is order-safe
The executor walks tools in receipt order and yields completed results once prior ordering constraints are satisfied.

### Rewrite requirement
Preserve stable, receipt-order-based final result delivery.

---

## 10.2 Once yielded, a tool transitions to a terminal `yielded` state
This distinguishes tools whose final output has entered the transcript from tools that are merely completed internally.

### Rewrite requirement
Preserve a post-completion yielded state.

---

## 10.3 Tool-use IDs are marked complete only after final result yield
The in-progress tool-use set is only cleared when the result has actually been yielded.

### Rewrite requirement
Preserve separation between internal completion and externally yielded completion.

---

## 11. Interruptibility semantics

## 11.1 Tools have interrupt behavior (`cancel` or `block`)
The executor distinguishes tools that may be cancelled on user interruption from tools that block interruption.

### Rewrite requirement
Preserve per-tool interrupt policy in streaming execution.

---

## 11.2 UI/interruption state reflects whether all currently executing tools are cancelable
The runtime updates a “has interruptible tool in progress” style flag based on whether the executing set is fully cancelable.

### Rewrite requirement
Preserve executor-driven interruptibility reporting to the surrounding runtime/UI.

---

## 11.3 User submit-interrupts only synthesize cancellation for tools whose policy allows it
If the abort reason is an interrupt/new-message submission, only tools with `cancel` interrupt behavior are turned into synthetic user-interrupted results.

### Rewrite requirement
Preserve policy-aware cancellation on submit-interrupt.

---

## 12. Synthetic error result generation

The executor can synthesize error tool_results for at least these reasons:
- unknown tool
- sibling tool failure cascade
- user interruption
- streaming fallback / discarded attempt

### Rewrite requirement
Preserve synthetic tool_result generation for all abandonment/error paths so every emitted tool_use closes.

---

## 12.1 User interruption uses rejection-style messaging
For user-triggered interruption/rejection, the runtime uses a rejection-style synthetic result so the user-facing semantics match “rejected/cancelled” rather than a generic execution crash.

### Rewrite requirement
Preserve distinct messaging semantics for user rejection/interruption versus generic execution failure.

---

## 12.2 Streaming fallback discard uses an explicit discarded-attempt result
If a streaming attempt is discarded due to fallback/attempt abandonment, tools from that attempt are closed with explicit discarded/fallback synthetic results.

### Rewrite requirement
Preserve explicit discarded-attempt closure semantics.

---

## 13. Sibling-failure cascade behavior

## 13.1 A tool can fail without cancelling siblings unless policy says otherwise
Not every tool error nukes the rest of the executing tool set.

### Rewrite requirement
Preserve selective sibling-cancel policy rather than universal cascade.

---

## 13.2 Bash failures are treated specially and can cancel sibling tools
Bash is treated as a dependency-heavy tool; an error in Bash may abort sibling executions because subsequent work is often rendered pointless or unsafe.

### Rewrite requirement
Preserve tool-type-specific sibling-cancel policy, especially for shell execution.

---

## 13.3 The tool that caused the error should not also receive a duplicate sibling-error synthetic result
The executor tracks whether the failing tool already produced its own error result, so it does not also get a second synthetic “cancelled due to sibling error” message.

### Rewrite requirement
Preserve no-double-error-result behavior for the originating failing tool.

---

## 14. Abort-controller topology

## 14.1 Each running tool gets its own child abort controller
Every tool execution runs under a per-tool child controller rather than sharing only one global query abort signal.

### Rewrite requirement
Preserve per-tool child abort controllers.

---

## 14.2 There is also a sibling-abort controller beneath the query-level controller
A dedicated sibling-abort controller lets one tool cascade-cancel siblings without necessarily terminating the entire query immediately.

### Rewrite requirement
Preserve separate sibling-cancel and query-cancel control paths.

---

## 14.3 Some tool-level aborts bubble up to the query abort controller
If a tool abort is not merely a sibling-cancel/discard case, it can propagate back to the query-level controller so the outer turn can terminate correctly.

### Rewrite requirement
Preserve upward abort propagation for tool-level rejections that semantically abort the turn.

---

## 15. Discarding an abandoned streaming attempt

## 15.1 Discard marks the executor as no longer owning any future transcript output
When a streaming attempt is abandoned, the executor is marked discarded and its pending/in-progress work is treated as belonging to a dead attempt.

### Rewrite requirement
Preserve explicit executor discard state on abandoned attempts.

---

## 15.2 Discard prevents further normal result emission from that executor
A discarded executor should not continue yielding ordinary results into the surviving transcript.

### Rewrite requirement
Preserve hard attempt ownership boundaries after discard.

---

## 15.3 The surrounding query loop must replace the executor after discard
A discarded executor is not reused. A new executor is created for the surviving stream/attempt.

### Rewrite requirement
Preserve executor instance replacement across abandoned attempts.

---

## 16. Interaction with partial assistant state

## 16.1 Tool results are associated with the assistant message that emitted the originating tool use
Tracked tools retain the source assistant message identity so emitted tool_results can be correctly linked back to that assistant turn.

### Rewrite requirement
Preserve source-assistant linkage for streamed tool results.

---

## 16.2 If the assistant stream is abandoned, already-yielded partial assistant messages may be tombstoned
The query loop can tombstone partial assistant output from a failed stream while also discarding that attempt’s executor.

### Rewrite requirement
Preserve coordinated cleanup of partial assistant state and streaming tool executor state on abandoned streams.

---

## 17. Context modifier application

## 17.1 Tool execution can produce context modifiers in addition to messages
A tool run may return context-modifier functions that update tool-use context for subsequent execution.

### Rewrite requirement
Preserve separate handling of emitted messages and context modifiers.

---

## 17.2 Context modifiers are applied conservatively for non-concurrent tools
The current behavior applies collected context modifiers directly for non-concurrent tools once they complete.

### Rewrite requirement
Preserve conservative context mutation rules; do not assume concurrent context modifiers can be merged arbitrarily.

---

## 18. Waiting strategy for remaining results

## 18.1 The executor yields ready progress/results non-blockingly first
Before waiting, it drains anything already available.

### Rewrite requirement
Preserve drain-before-wait behavior.

---

## 18.2 If nothing is currently yieldable, the executor waits for either tool completion or new progress
The executor races in-flight tool promises against a progress-availability signal.

### Rewrite requirement
Preserve wake-up on progress as well as completion.

---

## 18.3 The executor continues until all tools have reached yielded state
The outer remaining-results loop ends only when every tracked tool has fully passed through final result delivery.

### Rewrite requirement
Preserve completion criterion based on yielded state, not merely completed execution.

---

## 19. Relationship to turn retry/fallback semantics

## 19.1 Streaming tool execution is attempt-local
Results from one streaming attempt must never leak into a later fallback/retry attempt unless they are intentionally regenerated there.

### Rewrite requirement
Preserve attempt-local ownership of all streamed tool results.

---

## 19.2 Abandoned attempts must still close already-emitted tool_use blocks
Even if the attempt dies, those tool uses need synthetic tool_results.

### Rewrite requirement
Preserve tool_use/tool_result closure across abandoned streaming attempts.

---

## 19.3 Streaming execution does not weaken the standard turn-level invariants
All the invariants from the broader query state machine still apply:
- no orphaned tool_use blocks
- no stale results crossing fallback boundaries
- abort must produce coherent transcript state

### Rewrite requirement
Preserve compatibility between streaming executor behavior and the broader turn-failure state machine.

---

## 20. Suggested clean-room interfaces

A rewrite should expose interfaces roughly like:

```ts
interface StreamingToolExecutor {
  addTool(block: ToolUseBlock, assistantMessage: AssistantMessage): void
  discard(): void
  getCompletedResults(): Generator<MessageUpdate, void>
  getRemainingResults(): AsyncGenerator<MessageUpdate, void>
  getUpdatedContext(): ToolUseContext
}

type MessageUpdate = {
  message?: Message
  newContext?: ToolUseContext
}

type ToolStatus = 'queued' | 'executing' | 'completed' | 'yielded'
```

And tool definitions should expose policies roughly like:

```ts
interface ToolExecutionPolicy {
  isConcurrencySafe(input: unknown): boolean
  interruptBehavior(): 'cancel' | 'block'
}
```

---

## 21. Critical invariants to preserve

## 21.1 Every streamed tool_use must still end in exactly one tool_result envelope for that tool use
Failure mode:
- invalid transcript/tool trajectory

## 21.2 Progress and final result channels must remain distinct
Failure mode:
- result ordering becomes nondeterministic or UI semantics become confusing

## 21.3 Discarded executors must not leak ordinary results into the surviving attempt
Failure mode:
- stale tool results attached to wrong attempt/tool_use IDs

## 21.4 Non-concurrent tools must create queue barriers
Failure mode:
- stateful tools interleave unsafely

## 21.5 Interruptibility must respect per-tool policy
Failure mode:
- tools get cancelled when they should block, or vice versa

## 21.6 Sibling-cancel policy must be selective, not universal
Failure mode:
- one harmless tool failure needlessly collapses the entire parallel batch

## 21.7 Tool-use completion should only be marked after final result yield
Failure mode:
- runtime/UI thinks a tool is done before its result is actually in transcript state

---

## 22. Confidence and limits

High confidence:
- executor state model, concurrency rules, progress buffering, yielded-state distinction, synthetic error generation, sibling-abort behavior, discard semantics, and per-tool child abort controllers are directly grounded in inspected code

Moderate confidence:
- the exact upstream parsing event that causes a streamed tool-use block to become “ready” is described here at the behavioral level rather than reconstructed from the full stream parser implementation in this pass

That is acceptable because this document is intended to preserve the externally relevant execution semantics of streamed tool handling rather than every parser-internal detail.
