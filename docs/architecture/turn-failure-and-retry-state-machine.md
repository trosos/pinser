# Turn failure and retry state machine for a clean-room rewrite

This document captures how a single query/turn behaves when things go wrong: API overload, prompt overflow, max-output truncation, fallback-model switching, aborts, tool-result repair, and stop-hook interactions.

It is intended as a behavioral specification for a compatible rewrite.

Companion docs:
- `docs/hld.md`
- `docs/interfaces-and-endpoints.md`
- `docs/message-normalization-for-api.md`
- `docs/session-compaction-and-recovery.md`
- `docs/conversation-recovery-state-machine.md`
- `docs/agent-resume-and-sidechains.md`

Primary inspected sources for this pass:
- `src/query.ts`
- `src/query/stopHooks.ts`
- `src/services/api/withRetry.ts`
- `src/cli/structuredIO.ts`
- `src/services/tools/StreamingToolExecutor.ts` (indirectly via query loop behavior)

---

## 1. Scope

This document is specifically about the **single-turn execution state machine**.

It does **not** primarily describe:
- transcript persistence format
- resume loading
- session compaction persistence
- permission rule storage

Instead it describes what the runtime does during one query when failures or retries occur.

---

## 2. Core design principle

The implementation treats a turn as a state machine, not a linear request.

A turn may:
- preprocess history
- call the model
- stream assistant output
- execute tools while streaming or after streaming
- retry the same request under a different model
- compact and retry with rewritten history
- inject repair messages
- recover from truncation
- abort cleanly while maintaining message-shape invariants
- run stop hooks only for successful non-error endings

### Rewrite requirement
Preserve turn execution as an explicit state machine with **typed continuation reasons**, not as a recursive pile of ad hoc retry calls.

---

## 3. Loop state that must exist

A compatible rewrite should maintain loop state equivalent to:

```ts
type TurnState = {
  messages: Message[]
  toolUseContext: ToolUseContext
  autoCompactTracking?: AutoCompactTrackingState
  maxOutputTokensRecoveryCount: number
  hasAttemptedReactiveCompact: boolean
  maxOutputTokensOverride?: number
  pendingToolUseSummary?: Promise<ToolUseSummaryMessage | null>
  stopHookActive?: boolean
  turnCount: number
  transition?: Continue
}
```

Important fields:
- `messages`: current input history for the next attempt
- `autoCompactTracking`: compaction circuit-breaker state across retries
- `hasAttemptedReactiveCompact`: one-shot guard against compact/retry loops
- `maxOutputTokensOverride`: escalated output cap for retry
- `pendingToolUseSummary`: asynchronously generated summary from prior tool batch
- `stopHookActive`: tells the next iteration that stop-hook retry is in progress
- `transition`: machine-readable reason why the previous iteration continued

### Rewrite requirement
Preserve explicit per-turn mutable state with continuation metadata.

---

## 4. High-level turn state machine

A compatible rewrite should behave roughly like:

```ts
while (true) {
  prepareMessages()
  maybeCompactOrCollapse()
  maybeBlockForContextLimit()

  const streamResult = callModelAndConsumeStream()

  if (streamResult.aborted) return aborted
  if (streamResult.retryWithFallback) continue
  if (streamResult.apiErrorRecoverableByCompaction) continue
  if (streamResult.apiErrorRecoverableByResume) continue
  if (streamResult.noToolFollowUpNeeded) {
    maybeRunStopHooksOrReturn()
    continueOrReturn()
  }

  const toolResult = runTools()
  if (toolResult.preventContinuation) return
  continueWithToolResults()
}
```

The concrete machinery is more detailed, but this is the governing shape.

---

## 5. Request-attempt state machine

Within one loop iteration, the model-call portion itself has nested retry behavior:

```ts
attemptWithFallback = true
while (attemptWithFallback) {
  attemptWithFallback = false
  try {
    streamModelResponse()
  } catch (err) {
    if (err is FallbackTriggeredError && fallbackModel configured) {
      switchModel()
      repairOrphanedToolUseBlocks()
      clearPartialAssistantState()
      retrySameIteration()
    } else {
      throw err
    }
  }
}
```

This is distinct from the outer query-loop continuation.

### Rewrite requirement
Preserve the distinction between:
- retrying the **same iteration** under fallback model
- continuing the **outer loop** with rewritten history/state

---

## 6. API retry semantics before control returns to the turn loop

The lower API layer (`withRetry`) already retries many transient failures before the higher query loop sees anything.

## 6.1 Retryable classes
The API retry layer handles at least:
- network/connection failures that the SDK marks retryable
- 429 rate-limit responses
- 529 overload responses
- some auth-refresh situations (401/revoked OAuth/credential refresh cases)
- stale keep-alive socket failures such as `ECONNRESET` / `EPIPE`
- context-overflow 400s that can be converted into a reduced max-token retry

### Rewrite requirement
Preserve a dedicated lower retry layer beneath the turn state machine.

---

## 6.2 Foreground-only 529 retry policy
Not every query source retries overloads equally.

Foreground/user-blocking sources retry 529. Background/non-user-visible sources generally bail immediately to avoid overload amplification.

Examples of foreground-retried sources include:
- main REPL turn
- SDK turn
- agent turns
- compact/session-critical helper flows
- hook/verification/side-question style flows
- certain security classifiers required for correctness

### Rewrite requirement
Preserve source-aware overload retry policy rather than retrying every helper job indiscriminately.

---

## 6.3 Exponential backoff with jitter
The retry layer uses exponential backoff with jitter, with server `Retry-After` honored when present.

### Rewrite requirement
Preserve backoff+jitter, and preserve honoring server `Retry-After` directives.

---

## 6.4 Persistent unattended retry mode is distinct from normal retry mode
When an unattended/persistent retry feature is enabled, transient capacity errors can retry indefinitely with long capped waits and periodic keep-alive progress emission.

This is not the normal interactive retry path.

### Rewrite requirement
Preserve a distinct unattended retry mode if the rewrite retains unattended execution semantics.

---

## 6.5 Persistent retry emits periodic heartbeat-style status during long waits
Long waits are chunked so the host sees periodic output rather than considering the session idle.

### Rewrite requirement
Preserve chunked sleep / heartbeat progress behavior during long unattended retry waits.

---

## 7. Fast-mode fallback semantics

When fast mode is active, 429/529 handling is not just “retry later”.

The retry layer may:
- keep fast mode active for short retry windows to preserve prompt cache locality
- disable fast mode / enter cooldown for longer or unknown retry windows
- permanently disable fast mode when the API explicitly rejects fast mode entitlement
- disable fast mode when overage usage is unavailable

### Rewrite requirement
Preserve fast-mode-specific retry/cooldown semantics separately from ordinary retry logic.

---

## 8. Fallback-model trigger semantics

## 8.1 Fallback triggering is based on repeated overload, not generic failure
The lower retry layer can throw a dedicated `FallbackTriggeredError` after repeated overload conditions, especially for configured primary models that support fallback.

This is not used for arbitrary errors.

### Rewrite requirement
Preserve a dedicated typed fallback trigger rather than encoding fallback through string matching.

---

## 8.2 Fallback happens within the current iteration
When fallback triggers:
- current model is switched to fallback model
- the current streaming attempt is discarded
- partial assistant state is cleared
- orphan tool-use blocks are repaired with synthetic tool_result errors
- tool executor state is reset
- protected thinking/signature blocks may be stripped before replay
- a warning/system message is emitted to the user
- the same iteration retries immediately

### Rewrite requirement
Preserve in-iteration model fallback semantics.

---

## 8.3 Fallback retry must repair tool-use invariants
If assistant output from the abandoned attempt already emitted tool_use blocks, the implementation emits matching error tool_result blocks before retrying.

The repair text used in this path is equivalent to:
- `Model fallback triggered`

### Rewrite requirement
Preserve the invariant that every emitted tool_use must eventually receive a tool_result, even on fallback retries.

---

## 8.4 Fallback retry clears streaming executor state
Any queued/completed tool results from the abandoned attempt are discarded and the streaming tool executor is recreated.

Otherwise stale tool_result blocks could leak into the fallback response and reference obsolete tool_use IDs.

### Rewrite requirement
Preserve executor reset on fallback retry.

---

## 8.5 Protected thinking blocks may need stripping before fallback replay
Thinking/signature blocks can be model-bound. Replaying a protected-thinking block across incompatible models can hard-fail the retry.

### Rewrite requirement
Preserve model-switch-safe stripping or equivalent normalization of protected thinking/signature data before fallback replay.

---

## 9. Streaming fallback inside a single API request

Separate from full fallback-model retry, the API layer can signal a streaming fallback condition mid-stream.

When that happens, the turn loop:
- tombstones all already-yielded assistant partials from the failed stream
- clears assistantMessages/toolResults/toolUseBlocks
- discards and recreates the streaming tool executor
- continues consuming the fallback stream

### Rewrite requirement
Preserve tombstoning of orphaned partial assistant messages when a stream is abandoned mid-flight.

---

## 10. Error surfacing model

## 10.1 Not all API failures are surfaced immediately
Certain errors are intentionally withheld from the user stream because the runtime may still recover.

Withheld classes include at least:
- prompt-too-long / context overflow that can be recovered by collapse or reactive compact
- media-size overflow recoverable by reactive compact/media stripping
- max_output_tokens truncation recoverable by retry/escalation

### Rewrite requirement
Preserve withheld-error behavior for recoverable failures.

---

## 10.2 Withheld errors are still stored in assistantMessages
Even when the user does not see the error immediately, the message is retained in loop state so post-stream recovery logic can inspect it.

### Rewrite requirement
Preserve separation between “suppressed from output” and “retained for control flow”.

---

## 11. Prompt-too-long recovery state machine

## 11.1 Prompt-too-long is recovered after streaming ends, not during the stream
The stream loop withholds the error. The decision is made after the request finishes.

### Rewrite requirement
Preserve post-stream prompt-too-long recovery.

---

## 11.2 Context-collapse drain gets first chance
If context-collapse has staged collapses available, the runtime first drains/commits them and retries the turn.

This is cheaper and more granular than full reactive compact.

### Rewrite requirement
Preserve collapse-drain-before-reactive-compact ordering if the rewrite retains both systems.

---

## 11.3 Collapse drain is single-shot per failure chain
The implementation checks the previous continuation reason and will not repeatedly do collapse-drain retry if it already did so and the retried request still overflowed.

Continuation reason used here is equivalent to:
- `collapse_drain_retry`

### Rewrite requirement
Preserve guard against repeated collapse-drain loops.

---

## 11.4 Reactive compact is the second recovery stage
If collapse drain is unavailable or insufficient, reactive compact is attempted.

If it succeeds:
- compact boundary/summary messages are yielded
- loop state is replaced with post-compact messages
- `hasAttemptedReactiveCompact` becomes true
- the outer loop continues

Continuation reason used here is equivalent to:
- `reactive_compact_retry`

### Rewrite requirement
Preserve one-shot reactive compact retry semantics.

---

## 11.5 Prompt-too-long recovery must not spiral
If recovery fails:
- the withheld error is surfaced
- stop-failure hooks may be notified
- the turn returns immediately
- ordinary stop hooks are **not** run

Reason:
- stop hooks would inject more content into an already-overflowing context and create a death spiral

### Rewrite requirement
Preserve early-return on unrecovered prompt-too-long errors, with no ordinary stop-hook execution.

---

## 12. Media-size recovery state machine

Media/image/PDF/too-many-image failures use similar withholding semantics but skip the context-collapse drain stage.

Reason:
- collapse does not remove oversized media; reactive compact/media stripping does

If reactive compact succeeds, retry with compacted/stripped history.
If not, surface the error and return without ordinary stop hooks.

### Rewrite requirement
Preserve media-error recovery as a reactive-compact-only path.

---

## 13. Max-output-tokens recovery state machine

## 13.1 Max-output-tokens errors are withheld initially
The assistant API error for `max_output_tokens` is not immediately shown if recovery may continue.

### Rewrite requirement
Preserve withholding of recoverable max-output-tokens errors.

---

## 13.2 First recovery stage may escalate the output cap in-place
If no explicit max-output-token override is already active, the runtime may retry the same request with an elevated output-token cap.

Continuation reason used here is equivalent to:
- `max_output_tokens_escalate`

### Rewrite requirement
Preserve a one-shot “retry with larger output cap” stage if the rewrite retains this optimization.

---

## 13.3 Second recovery stage injects a meta resume instruction
If escalation is unavailable or insufficient, the runtime appends a meta user message instructing the model to continue directly without apology or recap and to break work into smaller pieces.

Continuation reason used here is equivalent to:
- `max_output_tokens_recovery`

The retry counter is incremented.

### Rewrite requirement
Preserve explicit continuation-message-based recovery for truncation.

---

## 13.4 Recovery attempts are bounded
The runtime caps these continuation recoveries to a fixed small number.

After exhaustion:
- the withheld max-output-tokens error is surfaced
- no further continuation is attempted

### Rewrite requirement
Preserve bounded truncation-recovery attempts.

---

## 14. Context-overflow 400 adjustment in the lower retry layer

Separate from prompt-too-long turn recovery, the lower retry layer can parse an older-style context-overflow 400 error and retry with reduced `max_tokens` for the request.

That logic:
- extracts input-tokens and context-limit from the error
- applies a safety buffer
- ensures a minimum floor
- preserves enough room for thinking budget plus at least one output token
- stores the override in retry context for the next attempt

### Rewrite requirement
Preserve this lower-level adjustment path if the target API surface still emits such errors.

---

## 15. Blocking-limit preemption before the API call

When automatic compaction/recovery is disabled or unavailable, the turn loop can preemptively block the request before calling the model if estimated context usage is already beyond the hard blocking limit.

Important exceptions:
- skip after a compaction that already produced a safe window
- skip for compact/session-memory helper queries that must run even when context is huge
- skip when reactive compact or context-collapse owns the overflow-recovery path

### Rewrite requirement
Preserve pre-flight blocking only when no automatic recovery mechanism is expected to handle the overflow.

---

## 16. Abort / interruption semantics

## 16.1 Abort is checked before each retry attempt
The lower retry layer and the turn loop both honor `AbortSignal`.

### Rewrite requirement
Preserve abort propagation at every retry layer.

---

## 16.2 Aborting after assistant tool_use emission must still repair tool-result shape
If streaming is aborted after tool_use blocks were emitted:
- when using streaming tool execution, remaining executor results are drained so synthetic aborted tool_results are emitted
- otherwise synthetic tool_result errors are emitted directly

Repair text in the non-streaming path is equivalent to:
- `Interrupted by user`

### Rewrite requirement
Preserve tool_use/tool_result pairing even on abort.

---

## 16.3 User interruption emits a dedicated interruption message unless this was a submit-interrupt
For normal aborts, the runtime yields a user interruption message.
For submit-interrupts, it suppresses that extra message because the queued user message that follows already explains the interruption.

### Rewrite requirement
Preserve distinction between generic interrupt and submit-interrupt behavior.

---

## 16.4 Abort exits before stop hooks
Once the stream is aborted and repair messages are emitted, the turn returns immediately.

### Rewrite requirement
Preserve no-stop-hooks-on-abort behavior.

---

## 17. Tool-use / tool-result invariants during failure

## 17.1 Every emitted tool_use must have a corresponding tool_result
This invariant is repaired on:
- fallback-model retry
- generic thrown query error after tool_use emission
- user abort
- streaming executor abort paths

### Rewrite requirement
Preserve unconditional tool_use/tool_result closure.

---

## 17.2 Generic thrown errors also repair tool-use closure before surfacing the real error
If an unexpected exception escapes the model call path:
- synthetic tool_result error blocks are emitted for all outstanding tool_use blocks
- then the actual error is surfaced as an assistant API error message

This avoids misleading clients into thinking the request was merely interrupted.

### Rewrite requirement
Preserve tool-result repair before final error surfacing on exceptional paths.

---

## 17.3 Streaming executor state must never survive across abandoned attempts
Whenever an attempt is abandoned, the executor is discarded and recreated.

### Rewrite requirement
Preserve executor instance reset across abandoned attempts.

---

## 18. No-tool-follow-up terminal path

When streaming completes and no tool follow-up is required, the runtime examines the final assistant message.

Possible branches:
- prompt-too-long recovery
- media recovery
- max-output-tokens recovery
- terminal API error handling
- ordinary stop hooks
- token-budget continuation
- completed return

### Rewrite requirement
Preserve this post-stream branch point as the main “end of assistant turn” decision node.

---

## 19. API-error terminal path skips ordinary stop hooks

If the last assistant message is an API error and recovery has been exhausted or is not applicable:
- stop-failure hooks may run
- ordinary stop hooks do not run
- the turn returns

Reason:
- hooks are for evaluating a valid assistant response, not a transport/capacity/auth failure

### Rewrite requirement
Preserve separation between stop-failure hooks and ordinary stop hooks.

---

## 20. Ordinary stop-hook state machine

Ordinary stop hooks run only after a non-error assistant completion with no pending tool follow-up.

Possible outcomes:
- `preventContinuation = true` → immediate terminal return
- blocking errors produced → append them to history and continue outer loop
- no blocking errors → continue to token-budget logic / completion

Continuation reason used here is equivalent to:
- `stop_hook_blocking`

### Rewrite requirement
Preserve stop-hook blocking as a first-class continuation state.

---

## 21. Stop-hook retry must preserve reactive-compact guard state

If a prior reactive compact already happened and still did not fix prompt-too-long behavior, a subsequent stop-hook blocking retry must not reset `hasAttemptedReactiveCompact` to false.

Otherwise the next iteration can enter an infinite loop:
- compact
- still too long
- hook blocking message added
- retry
- compact again
- still too long
- ...

### Rewrite requirement
Preserve reactive-compact-attempt state across stop-hook retries.

---

## 22. Token-budget continuation state

After ordinary stop hooks succeed, the runtime may still choose to continue the turn automatically due to token-budget policy.

If continuation is chosen:
- a meta nudge message is appended
- turn state continues
- truncation recovery counters reset appropriately

Continuation reason used here is equivalent to:
- `token_budget_continuation`

### Rewrite requirement
Preserve token-budget continuation as separate from failure recovery.

---

## 23. Tool-execution continuation path

When tool_use blocks were produced, the runtime executes tools and then continues the outer loop with:
- prior `messagesForQuery`
- streamed assistant messages
- normalized tool result messages
- updated tool context if tools changed it
- new pending tool-use summary promise if enabled

This is not a failure path, but it is part of the continuation state machine.

### Rewrite requirement
Preserve outer-loop continuation after tool execution instead of recursive re-entry.

---

## 24. Transition reasons that should remain explicit

A compatible rewrite should preserve machine-readable continuation reasons equivalent to:

```ts
type ContinueReason =
  | { reason: 'collapse_drain_retry'; committed: number }
  | { reason: 'reactive_compact_retry' }
  | { reason: 'max_output_tokens_escalate' }
  | { reason: 'max_output_tokens_recovery'; attempt: number }
  | { reason: 'stop_hook_blocking' }
  | { reason: 'token_budget_continuation' }
```

The exact union can be larger, but these reasons are important because behavior depends on them, not just logs.

### Rewrite requirement
Preserve typed continuation reasons in runtime state.

---

## 25. Terminal reasons that should remain explicit

A compatible rewrite should preserve terminal outcomes equivalent to:

```ts
type TerminalReason =
  | { reason: 'completed' }
  | { reason: 'blocking_limit' }
  | { reason: 'prompt_too_long' }
  | { reason: 'image_error' }
  | { reason: 'aborted_streaming' }
  | { reason: 'stop_hook_prevented' }
  | { reason: 'model_error'; error: unknown }
```

Exact names can differ, but the semantics should remain separate.

### Rewrite requirement
Preserve terminal-result classification instead of collapsing all failures into a single generic error result.

---

## 26. Suggested clean-room interfaces

A rewrite should expose interfaces roughly like:

```ts
interface RetryLayer {
  runWithRetry<T>(
    operation: (attempt: number, context: RetryContext) => Promise<T>,
    options: RetryOptions,
  ): AsyncGenerator<SystemAPIErrorMessage, T>
}

interface TurnStateMachine {
  runTurn(params: QueryParams): AsyncGenerator<TurnEvent, Terminal>
}

interface Continue {
  reason: string
}

interface Terminal {
  reason: string
  error?: unknown
}
```

And it should preserve a typed fallback trigger such as:

```ts
class FallbackTriggeredError extends Error {
  originalModel: string
  fallbackModel: string
}
```

---

## 27. Most critical invariants for a rewrite

## 27.1 Every emitted tool_use must receive a tool_result, even on failure
Failure mode:
- downstream clients/transcript consumers see invalid tool trajectories

## 27.2 Recoverable API errors must be withheld until recovery is exhausted
Failure mode:
- clients prematurely terminate even though the runtime intended to continue

## 27.3 Prompt-too-long recovery must not run ordinary stop hooks on failure
Failure mode:
- infinite error/hook/retry growth spiral

## 27.4 Reactive compact must be one-shot per failure chain unless state is explicitly reset
Failure mode:
- repeated compact/retry loops burning API calls

## 27.5 Fallback-model retries must discard orphaned partial assistant and tool executor state
Failure mode:
- stale tool results, invalid thinking blocks, corrupted transcript/UI state

## 27.6 Abort handling must repair tool-result shape before returning
Failure mode:
- incomplete assistant trajectories on interrupt

## 27.7 Long unattended retries need heartbeat output during waits
Failure mode:
- host/orchestrator treats the session as dead or idle and kills it

## 27.8 Background/non-user-visible queries must not amplify overload with aggressive retries
Failure mode:
- self-inflicted cascading load during capacity incidents

---

## 28. Confidence and limits

High confidence:
- fallback-model retry behavior, withheld-error handling, prompt-too-long/media/max-output recovery, abort repair semantics, stop-hook skipping on API error, source-aware 529 retry, persistent unattended retry, and tool_use/tool_result closure are directly grounded in inspected code

Lower confidence:
- some details of the streaming-tool executor internals are inferred from the surrounding query-loop behavior rather than exhaustively restated from its implementation here

That is deliberate: this document is the turn-level state-machine spec, not a line-by-line tool executor spec.
