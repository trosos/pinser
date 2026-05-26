# Model and request shaping for a clean-room rewrite

This document captures how a turn is shaped into a model API request: system prompt block construction, context injection, tool schema serialization, beta/header gating, cache-control shaping, thinking/task-budget parameters, and request-stability rules intended to preserve cache hits and avoid provider incompatibilities.

It is intended as a behavioral spec for a compatible clean-room rewrite.

Companion docs:
- `docs/hld.md`
- `docs/interfaces-and-endpoints.md`
- `docs/remote-api.md`
- `docs/message-normalization-for-api.md`
- `docs/tool-result-budgeting-and-dedup.md`
- `docs/turn-failure-and-retry-state-machine.md`

Primary inspected sources for this pass:
- `src/query.ts`
- `src/query/config.ts`
- `src/utils/api.ts`
- `src/utils/systemPrompt.ts`
- `src/utils/thinking.ts`
- `src/bootstrap/state.ts`
- `src/cli/print.ts`

---

## 1. Scope

This document is about the **request-shaping layer** between in-memory conversation state and the outbound model API call.

It focuses on:
- system prompt block assembly and splitting
- user/system context injection
- message selection and final `messagesForQuery` shaping
- tool schema generation and per-request overlays
- prompt-cache-aware request stability
- thinking and task-budget request parameters
- feature/beta/provider gating for request fields
- fallback and retry interactions that modify request shape

It is not primarily about:
- persistence format
- permissioning
- tool sandboxing
- retry/backoff timing

---

## 2. Core design principle

The runtime does not build requests by simply serializing the current transcript.

Instead, request construction is a policy layer that balances:
- correctness of conversation semantics
- provider compatibility
- prompt cache hit preservation
- rollout/beta safety
- token-budget protection
- structured tool interoperability

### Rewrite requirement
Preserve request building as a dedicated shaping pipeline, not an ad hoc `client.messages.create({...})` call assembled inline at each call site.

---

## 3. Canonical request-shaping pipeline

A compatible rewrite should conceptually behave like:

```ts
const history = selectRelevantMessages(turnState)
const budgetedHistory = applyToolResultBudget(history)
const compactedHistory = maybeApplySnipMicrocompactCollapseAutocompact(budgetedHistory)
const apiMessages = normalizeMessagesForAPI(prependUserContext(compactedHistory, userContext))
const apiSystem = splitAndAnnotateSystemPrompt(appendSystemContext(systemPrompt, systemContext))
const apiTools = buildToolSchemas(tools, requestContext)
const params = addModelThinkingBudgetCacheAndBetaParams({
  model,
  messages: apiMessages,
  system: apiSystem,
  tools: apiTools,
})
return callModel(params)
```

The real implementation interleaves some of these concerns, but the rewrite should preserve the semantics.

---

## 4. Request stability is a first-class concern

A major design goal is keeping large parts of the request byte-stable across turns when semantics have not changed, especially to preserve prompt-cache hits.

This affects:
- system prompt block partitioning
- which sections are cache-controlled
- tool schema caching and per-request overlays
- header/beta latching semantics
- avoiding unnecessary mid-session drift from feature flag changes

### Rewrite requirement
Preserve request stability as an explicit design goal, not just a side effect.

---

## 5. Final message set selection

## 5.1 The model does not always receive the full raw transcript
The runtime derives `messagesForQuery` from the turn state, generally starting from the messages after the most recent compact boundary rather than blindly sending the whole historical transcript.

### Rewrite requirement
Preserve a derived query-history view distinct from the full persisted transcript.

---

## 5.2 Tool-result budgeting is applied before final API normalization
Before the request is normalized for the API, the runtime applies aggregate tool-result budgeting/content replacement to the message stream.

### Rewrite requirement
Preserve tool-result budgeting as part of request shaping, not merely transcript storage.

---

## 5.3 Snip / microcompact / context-collapse / autocompact all shape the request view
Multiple context-reduction systems can transform the outgoing request history before the API call.

### Rewrite requirement
Preserve request-time context reduction as layered transforms over the derived history view.

---

## 6. System prompt assembly

## 6.1 Base system prompt and runtime system context are separate concepts
The runtime maintains a base system prompt and appends runtime system context to it before request shaping.

System context includes environment/runtime facts and is appended as additional content rather than mutating the base prompt definition itself.

### Rewrite requirement
Preserve separation between base system prompt definition and appended runtime system context.

---

## 6.2 Appended system context is flattened as key-value text
When system context is appended, it is rendered into textual `key: value` style content and added as additional system prompt material.

### Rewrite requirement
Preserve deterministic text rendering of system context so equivalent state produces equivalent system prompt bytes.

---

## 6.3 User context is injected as a meta user message, not merged into the system prompt
User-context material is prepended as a synthetic meta user message wrapped in a reminder-style envelope rather than merged into the system prompt.

This means the runtime maintains a distinction between:
- system-controlled instructions
- advisory per-turn user context

### Rewrite requirement
Preserve user-context injection as a prepended meta user message rather than as direct system-prompt mutation.

---

## 6.4 User-context injection is skipped in tests and when empty
The injection layer avoids changing message arrays in test mode and when no user-context entries exist.

### Rewrite requirement
Preserve no-op behavior for empty user context, and preserve test-environment determinism if the rewrite maintains a similar test contract.

---

## 7. System prompt block splitting and cache scope

## 7.1 The system prompt is split into multiple logical cache blocks
The runtime does not treat the final system prompt as a single undifferentiated string. It splits it into blocks with cache-scope metadata.

### Rewrite requirement
Preserve block-based system-prompt shaping with explicit cache metadata.

---

## 7.2 Attribution header is isolated from cache-scoped prompt body
A billing/attribution header block, when present, is separated from the rest of the system prompt and assigned no cache scope.

### Rewrite requirement
Preserve separate handling of attribution/billing header content from the instruction-bearing prompt body.

---

## 7.3 Known system-prompt prefixes are handled specially
Known CLI system-prompt prefix blocks are identified and separated from the remainder.

These prefixes influence prefix matching and cache behavior.

### Rewrite requirement
Preserve special recognition and stable placement of known system-prompt prefix blocks.

---

## 7.4 Dynamic-boundary marker enables split between globally-cacheable and dynamic system prompt regions
When a special boundary marker is present and global-cache mode is enabled, the system prompt is split into:
- non-cached attribution header
- non-cached known prefix block
- globally cached static content before the boundary
- non-cached dynamic content after the boundary

### Rewrite requirement
Preserve boundary-marker-driven partitioning between static and dynamic system prompt regions.

---

## 7.5 Missing boundary marker degrades safely to org-scoped caching
If global-cache mode is enabled but the boundary marker is absent, the runtime falls back to a simpler org-scoped prompt partition instead of failing.

### Rewrite requirement
Preserve safe fallback when static/dynamic boundary partitioning is unavailable.

---

## 7.6 MCP/tool-rich scenarios may intentionally skip global cache on the system prompt
When certain tool configurations are present, the runtime chooses tool-based/request-level cache behavior and avoids global cache scope on the system prompt.

### Rewrite requirement
Preserve the ability to disable global-cache system-prompt partitioning in tool-sensitive scenarios.

---

## 8. Prompt-cache preservation behavior

## 8.1 Mid-session feature flag flips should not churn request bytes unnecessarily
The implementation explicitly caches or latches request-shape components to avoid prompt-cache busting caused by stale or changing rollout flags mid-session.

### Rewrite requirement
Preserve session-stable request-shape decisions where mid-session toggles would otherwise cause semantically unnecessary cache misses.

---

## 8.2 Header/beta latching exists specifically to avoid double cache busts
Some request-affecting toggles are sticky-on once enabled so the runtime does not alternate between two cache keys as settings or server-side eligibility shift.

### Rewrite requirement
Preserve sticky/latching semantics for request-affecting toggles that would otherwise flap the cache key.

---

## 8.3 Cache-safe resume/retry paths reuse a stable request skeleton where possible
The runtime retains/cache-safes prior request parameters so follow-up calls can preserve identical prefix/system/tool schema bytes where semantics permit.

### Rewrite requirement
Preserve cache-safe parameter reuse on continuation flows if the rewrite keeps prompt-cache-aware optimizations.

---

## 9. Tool schema shaping

## 9.1 Tool schemas are not rebuilt from scratch for every request when avoidable
The runtime caches a session-stable base schema per tool (or per tool+JSON-schema identity for dynamic-schema tools) and applies per-request overlays later.

### Rewrite requirement
Preserve base-schema caching separate from per-request overlays.

---

## 9.2 Cache keys for tool schemas must include dynamic input schema when tool name alone is not sufficient
Some tools share a stable tool name but vary their JSON schema by workflow or call site. Name-only caching would return the wrong schema.

### Rewrite requirement
Preserve cache keys that include schema identity for dynamic-schema tools.

---

## 9.3 Tool schema has a session-stable base and a per-request overlay
The base schema covers stable fields such as:
- `name`
- `description`
- `input_schema`
- `strict`
- eager/fine-grained input streaming flags

The per-request overlay covers fields such as:
- `defer_loading`
- `cache_control`

### Rewrite requirement
Preserve a two-stage schema construction model: stable base + per-request overlay.

---

## 9.4 Tool descriptions are part of the request compatibility surface
The text returned by `tool.prompt(...)` is serialized into the model-facing tool schema and therefore affects both behavior and cache identity.

### Rewrite requirement
Treat tool descriptions/prompts as request-shaping inputs, not merely UI help text.

---

## 9.5 Swarm-only schema fields are conditionally stripped at request-shaping time
When swarm/agent features are not enabled, request-visible input schema fields related to those features are removed from certain tools.

### Rewrite requirement
Preserve runtime schema filtering for unavailable capabilities so external users do not see unsupported fields.

---

## 10. Structured-output and strict-tool gating

## 10.1 Strict tool schemas are only emitted when all gates agree
A tool is marked strict only if:
- the rollout/feature gate allows it
- the tool itself declares strict support
- the selected model supports structured outputs

### Rewrite requirement
Preserve multi-factor gating for strict/structured tool mode.

---

## 10.2 Unknown or unsupported models must not optimistically receive strict tool schemas
If model support is absent or unknown in the relevant path, the runtime behaves conservatively and omits strict mode.

### Rewrite requirement
Preserve conservative omission of strict mode when model capability is not established.

---

## 11. Fine-grained tool streaming request shaping

## 11.1 Fine-grained/eager tool input streaming is provider-gated
The runtime only emits the eager/fine-grained tool input streaming field under a restricted provider/configuration combination because some proxies/providers reject it.

### Rewrite requirement
Preserve provider-aware emission of fine-grained tool streaming request fields.

---

## 11.2 First-party-only experimental request fields must be suppressible centrally
There is a central kill switch that strips experimental request-shape fields from tool schemas before they go on the wire.

This is specifically to support proxy gateways or providers that reject extra fields.

### Rewrite requirement
Preserve a final choke point that can strip non-portable beta fields from tool schemas before serialization.

---

## 11.3 Standard cache control survives the experimental-beta strip, but beta subfields are separately gated
The implementation distinguishes between the base, widely-supported cache-control shape and more experimental subfields such as extended scope/TTL semantics.

### Rewrite requirement
Preserve separation between portable cache-control fields and narrower beta-only subfields.

---

## 12. Thinking parameter shaping

## 12.1 Thinking is a typed request-shaping mode, not a boolean toggle
The runtime models thinking configuration as one of:
- adaptive
- enabled with explicit budget tokens
- disabled

### Rewrite requirement
Preserve thinking as a typed config surface rather than a flat on/off flag.

---

## 12.2 Thinking support is provider- and model-aware
Support for thinking depends on provider/model capability rules and optional third-party overrides.

### Rewrite requirement
Preserve provider-aware and model-aware capability checks for thinking.

---

## 12.3 Adaptive thinking support is narrower than general thinking support
Only a subset of models support adaptive thinking; the runtime distinguishes this from basic thinking support.

### Rewrite requirement
Preserve separate capability checks for adaptive thinking versus general thinking.

---

## 12.4 Default thinking enablement is policy-driven
Thinking defaults are influenced by:
- explicit environment override
- user settings
- model policy defaults

### Rewrite requirement
Preserve a dedicated defaulting policy for thinking rather than inlining defaults per call site.

---

## 12.5 Thinking blocks impose request-history constraints
Thinking-related assistant blocks must be preserved consistently across the trajectory and require compatible request parameters on the turns that contain them.

### Rewrite requirement
Preserve the invariant that request shaping and history normalization remain consistent with the presence of thinking/redacted-thinking blocks.

---

## 13. Task-budget request shaping

## 13.1 API task budget is distinct from local auto-continuation token budget
The request layer supports an API-facing `task_budget` concept that is separate from the local token-budget continuation feature.

### Rewrite requirement
Preserve distinction between server-visible task budget parameters and local continuation heuristics.

---

## 13.2 After compaction, remaining task budget must be adjusted because the server no longer sees the summarized-away context window
Once compaction changes what history the server receives, the runtime tracks adjusted remaining task budget across subsequent iterations.

### Rewrite requirement
Preserve post-compaction task-budget correction if the target API surface includes whole-task budget semantics.

---

## 14. Model fallback and request reshaping

## 14.1 Fallback retry changes the model while trying to preserve as much of the request skeleton as possible
When fallback triggers, the model changes, but the runtime attempts to preserve the rest of the request semantics unless compatibility requires further normalization.

### Rewrite requirement
Preserve request-skeleton reuse across fallback retries where safe.

---

## 14.2 Protected thinking/signature blocks may need stripping before replay on a different model
Cross-model retry can require removal of model-bound protected-thinking/signature data before the next request is shaped.

### Rewrite requirement
Preserve model-switch-safe normalization before replaying assistant history on fallback model retries.

---

## 15. Provider and beta gating model

## 15.1 Build-time gates, rollout gates, env gates, and provider checks all participate in shaping
The request layer uses multiple control planes:
- build-time feature inclusion
- rollout/analytics gates
- environment kill switches
- provider capability checks
- model capability checks

### Rewrite requirement
Preserve these as separate concepts; do not collapse them into a single boolean flag source.

---

## 15.2 Some request fields are intentionally first-party-only
Certain request-shape features are emitted only against direct first-party API configurations and should not be assumed portable to Bedrock/Vertex/proxy providers.

### Rewrite requirement
Preserve provider-specific request-field compatibility rules.

---

## 15.3 Request shaping must degrade by omission, not by failure, on unsupported providers
When a provider does not support a field, the runtime generally strips or omits it rather than hard-failing request construction.

### Rewrite requirement
Preserve graceful omission of unsupported request-shape features.

---

## 16. Normalization boundary before API call

## 16.1 Messages are normalized for the API after all shaping transforms
The runtime applies message normalization only after the request history has been selected, compacted/budgeted, and context-injected.

### Rewrite requirement
Preserve API normalization as the last major transform before transport.

---

## 16.2 Request shaping depends on the model-visible representation, not just internal transcript objects
Budgeting, cache scope, and schema stability all care about what will actually be serialized to the model API.

### Rewrite requirement
Preserve shaping decisions based on the outbound serialized semantics.

---

## 17. Suggested clean-room interfaces

A rewrite should expose interfaces roughly like:

```ts
interface RequestShaper {
  shape(params: TurnRequestInput): ShapedModelRequest
}

interface SystemPromptShaper {
  appendContext(base: SystemPrompt, context: Record<string, string>): SystemPrompt
  split(prompt: SystemPrompt, options: SplitOptions): SystemPromptBlock[]
}

interface ToolSchemaBuilder {
  build(tool: Tool, options: ToolSchemaOptions): Promise<ApiToolSchema>
}

interface CapabilityPolicy {
  supportsThinking(model: string, provider: Provider): boolean
  supportsAdaptiveThinking(model: string, provider: Provider): boolean
  supportsStructuredTools(model: string, provider: Provider): boolean
}

interface RequestStabilityPolicy {
  latch(session: SessionState, next: ProposedRequestShape): StableRequestShape
}
```

And types roughly like:

```ts
type SystemPromptBlock = {
  text: string
  cacheScope: 'global' | 'org' | null
}

type ThinkingConfig =
  | { type: 'adaptive' }
  | { type: 'enabled'; budgetTokens: number }
  | { type: 'disabled' }
```

---

## 18. Critical invariants to preserve

## 18.1 System prompt partitioning must be deterministic
Failure mode:
- avoidable prompt-cache misses and inconsistent instruction ordering

## 18.2 Tool schemas must be stable across a session except for intentional per-request overlays
Failure mode:
- cache churn and hard-to-debug provider incompatibilities

## 18.3 Unsupported beta/provider fields must be omittable at one central choke point
Failure mode:
- request failures on proxies/3P providers

## 18.4 User context must remain distinct from the true system prompt
Failure mode:
- instruction-layer confusion and compatibility drift

## 18.5 Thinking-capability checks must be provider-aware
Failure mode:
- invalid requests or silent loss of quality-sensitive behavior

## 18.6 Task-budget correction after compaction must account for summarized-away context
Failure mode:
- incorrect server-side whole-task budget accounting

## 18.7 Request-shape decisions that affect cache keys should not flap mid-session without a semantic reason
Failure mode:
- repeated cache busting and degraded latency/cost

---

## 19. Confidence and limits

High confidence:
- system-prompt block splitting, context injection, tool-schema caching/overlay, strict-tool gating, first-party/provider-aware beta shaping, thinking capability policy, and post-compaction task-budget correction are directly grounded in inspected code

Moderate confidence:
- some broader request-stability motivations are synthesized from comments and surrounding state/latching code rather than rederived from every single transport call site in this pass

That is acceptable here because this document is intended to preserve clean-room request-shaping semantics, not to mirror every implementation detail verbatim.
