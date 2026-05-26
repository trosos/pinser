# Model selection and routing for a clean-room rewrite

This document captures how the runtime selects, resolves, validates, displays, and sometimes rewrites model choices across the main loop, plan mode, subagents, picker UX, and provider-specific environments.

It is intended as a behavioral spec for a compatible clean-room rewrite.

Companion docs:
- `docs/hld.md`
- `docs/interfaces-and-endpoints.md`
- `docs/model-and-request-shaping.md`
- `docs/agent-steering-and-work-coordination.md`
- `docs/remote-api.md`

Primary inspected sources for this pass:
- `src/utils/model/model.ts`
- `src/utils/model/modelOptions.ts`
- `src/utils/model/agent.ts`
- `src/utils/model/validateModel.ts`
- `src/commands/model/model.tsx`
- `src/commands/model/index.ts`
- `src/components/ModelPicker.tsx`
- `src/utils/fastMode.ts`

---

## 1. Scope

This document is about the **model decision layer**.

It covers:
- how the main model is chosen by default
- how user-specified settings override defaults
- how aliases are resolved into concrete provider-facing IDs
- how plan mode changes effective model selection at runtime
- how subagents inherit or reinterpret parent model choices
- how picker/options UX is generated from entitlement and provider state
- how validation and fallback suggestions work for custom model strings
- how fast mode constrains model compatibility

It is not primarily about:
- full request shaping beyond model choice
- transcript persistence
- tool permissions
- retry timing

---

## 2. Core design principle

The runtime does not treat “model” as a single opaque string.

Instead, it distinguishes several layers:
- **user setting / requested setting**
- **default logical setting for this account/provider**
- **resolved concrete model ID**
- **runtime-effective model for this turn**
- **display label shown to the user**

These layers intentionally differ.

For example:
- a stored value may be `opusplan`
- the resolved default may be Sonnet outside plan mode
- the runtime-effective model in plan mode may become Opus
- the picker label may say `Opus 4.6 in plan mode, else Sonnet 4.6`

### Rewrite requirement
Preserve model handling as a multi-layer policy system, not a single persisted string passed directly to the API.

---

## 3. Canonical model-resolution pipeline

A compatible rewrite should conceptually behave like:

```ts
const specified = getUserSpecifiedModelSetting() // maybe alias, maybe null, maybe undefined
const baseSetting = specified ?? getDefaultMainLoopModelSetting()
const resolvedMainLoopModel = parseUserSpecifiedModel(baseSetting)
const effectiveTurnModel = getRuntimeMainLoopModel({
  permissionMode,
  mainLoopModel: resolvedMainLoopModel,
  exceeds200kTokens,
})
```

And for subagents:

```ts
const effectiveAgentModel = getAgentModel(
  agentConfig.model,
  parentModel,
  toolSpecifiedModel,
  permissionMode,
)
```

### Rewrite requirement
Preserve a two-step distinction between:
1. resolving the configured/base main model
2. applying runtime turn-time rewrites such as plan-mode switching

---

## 4. Model layers that must remain distinct

## 4.1 Requested model setting
This is the value the user or caller specified through one of several control surfaces.

It may be:
- `undefined` meaning no user choice exists
- `null` meaning explicitly “default”
- a family alias like `sonnet`, `opus`, `haiku`
- a behavioral alias like `best` or `opusplan`
- a concrete provider-facing model ID
- a custom deployment/model name for a third-party provider

### Rewrite requirement
Preserve the semantic difference between `undefined` and `null`.

- `undefined` = no explicit choice; use built-in default policy
- `null` = explicit choice of “default”

---

## 4.2 Resolved main loop model
This is the concrete model string produced after alias resolution.

Examples:
- `sonnet` → provider-specific default Sonnet model
- `opus` → provider-specific default Opus model
- `haiku` → provider-specific default Haiku model
- `best` → current default Opus model
- `opusplan` → current default Sonnet model at base resolution time

### Rewrite requirement
Preserve alias resolution as a pure normalization step before runtime plan-mode overrides.

---

## 4.3 Runtime-effective model
The runtime-effective model can differ from the base resolved model depending on turn state.

Notable examples:
- `opusplan` becomes Opus in plan mode, but only under specific conditions
- `haiku` in plan mode upgrades to Sonnet
- `inherit` for a subagent can resolve through the parent thread’s runtime-effective model rather than simply copying the stored parent setting

### Rewrite requirement
Preserve runtime-effective selection as a separate decision layer.

---

## 4.4 Display model
The human-facing displayed value is not always identical to either the stored setting or the final wire model string.

Examples:
- `null` is shown as `... (default)`
- `opusplan` has a special human-readable label
- known model IDs map to public marketing names
- unknown custom models may display the literal string

### Rewrite requirement
Preserve dedicated display rendering rather than exposing raw internal strings directly everywhere.

---

## 5. Sources of truth and precedence

## 5.1 User-specified model precedence
The runtime computes the requested model setting with this priority order:

1. in-session model override from the `/model` command
2. startup override, such as a `--model` flag represented by bootstrap state
3. `ANTHROPIC_MODEL` environment variable
4. saved settings model value
5. built-in default policy if none of the above exist

If the chosen value is not permitted by the model allowlist, it is ignored and treated as if unspecified.

### Rewrite requirement
Preserve precedence order exactly:

```ts
session_override > startup_override > env_override > saved_settings > built_in_default
```

And preserve the allowlist guard before using a user-specified value.

---

## 5.2 Allowlist is applied before trusting configured model strings
A configured model that is outside the organization/user allowlist is not used, even if it came from environment or settings.

This means the system can silently fall back to built-in defaults when a previously valid stored value becomes disallowed.

### Rewrite requirement
Preserve allowlist filtering at the configured-model stage, not only in the picker UI.

---

## 6. Built-in default model policy

## 6.1 Default varies by account tier
The built-in default model setting is not global.

The policy is:
- internal/ant users: ant-specific configured default, otherwise Opus with `[1m]`
- Max users: Opus, optionally merged with `[1m]`
- Team Premium users: same as Max
- everyone else: Sonnet

“Everyone else” includes:
- Pro
- Team Standard
- Enterprise
- PAYG first-party
- PAYG third-party

### Rewrite requirement
Preserve tier-sensitive defaults.

Equivalent policy shape:

```ts
if (antUser) return antDefault ?? defaultOpus + '[1m]'
if (maxUser || teamPremiumUser) return defaultOpus + maybeMerged1mSuffix
return defaultSonnet
```

---

## 6.2 Provider affects what “default Sonnet” means
The default Sonnet differs by provider family.

Current behavior:
- first-party: default Sonnet is Sonnet 4.6
- third-party providers: default Sonnet is Sonnet 4.5

The reason is not semantic preference but provider lag/availability risk.

### Rewrite requirement
Preserve provider-aware default versioning, especially where first-party can move faster than Bedrock/Vertex/Foundry.

---

## 6.3 Provider can also affect default Opus and custom default env overrides
Default Opus and default Haiku are also defined through policy functions and may be overridden by environment variables.

The implementation currently keeps a dedicated third-party branch for Opus even when values happen to match, because divergence is expected over time.

### Rewrite requirement
Preserve dedicated provider-policy functions for each family, rather than hardcoding one global literal per family.

At minimum expose logic equivalent to:

```ts
getDefaultOpusModel()
getDefaultSonnetModel()
getDefaultHaikuModel()
```

---

## 6.4 Environment variables can replace default family targets
The following environment variables can replace family defaults:
- `ANTHROPIC_DEFAULT_OPUS_MODEL`
- `ANTHROPIC_DEFAULT_SONNET_MODEL`
- `ANTHROPIC_DEFAULT_HAIKU_MODEL`

Additional optional display metadata variables can also supply custom name/description text for picker UX.

### Rewrite requirement
Preserve the difference between:
- overriding the family default target
- overriding how that target is labeled/described in UI

---

## 7. Alias resolution semantics

## 7.1 Aliases are case-insensitive for recognized alias values
Known aliases are checked via lowercased, trimmed comparison.

The runtime recognizes a fixed alias set including at least:
- `sonnet`
- `opus`
- `haiku`
- `best`
- `opusplan`

And it supports a `[1m]` suffix layered onto aliases where applicable.

### Rewrite requirement
Preserve case-insensitive alias parsing while preserving case for non-alias custom model strings.

---

## 7.2 Alias resolution table
The effective alias mapping behaves like:

```ts
alias 'sonnet'   => getDefaultSonnetModel()
alias 'haiku'    => getDefaultHaikuModel()
alias 'opus'     => getDefaultOpusModel()
alias 'best'     => getDefaultOpusModel()
alias 'opusplan' => getDefaultSonnetModel() // base resolution, not plan-turn override
```

If the requested alias carries `[1m]`, the suffix is reattached after family resolution:

```ts
resolve(alias + '[1m]') => resolve(alias) + '[1m]'
```

### Rewrite requirement
Preserve this exact base mapping shape, especially the fact that `opusplan` resolves to Sonnet outside runtime plan-mode rewriting.

---

## 7.3 Non-alias custom model strings preserve original case
For custom model names, especially third-party deployment IDs, the runtime preserves the original casing.

It only strips and reapplies `[1m]` when present.

This matters for providers such as Foundry/Azure-style deployment identifiers where the string may be case-sensitive.

### Rewrite requirement
Do not lowercase arbitrary custom model strings during normalization.

---

## 7.4 Legacy first-party Opus strings are silently remapped
On first-party only, some explicit legacy Opus 4.0/4.1 identifiers are transparently rewritten to the current default Opus model, unless an opt-out environment variable disables this remap.

This remap does not apply to third-party providers.

Equivalent policy shape:

```ts
if (
  provider === 'firstParty' &&
  modelString is one of legacyExplicitOpusIds &&
  legacyRemapEnabled
) {
  return getDefaultOpusModel() + optional1mSuffix
}
```

### Rewrite requirement
Preserve legacy first-party explicit-Opus remapping as a compatibility behavior, not merely a picker convenience.

---

## 7.5 Skill and tool model-family overrides may carry over `[1m]`
When a skill requests a family like `opus` or `sonnet` and the current session model has `[1m]`, the runtime may carry `[1m]` to the target family if that family supports it.

This avoids accidental context-window downgrades caused by family-only overrides.

### Rewrite requirement
Preserve the invariant that family override semantics should not silently reduce context window when the target family supports the larger context.

---

## 8. Runtime model switching

## 8.1 Runtime selection depends on permission mode and token-window state
The runtime-effective model can differ from the resolved main loop model based on turn context.

The inspected function consumes:
- `permissionMode`
- `mainLoopModel`
- `exceeds200kTokens`

### Rewrite requirement
Preserve runtime model selection as a function of turn context, not just session configuration.

---

## 8.2 `opusplan` means “Sonnet by default, Opus in plan mode”
The alias `opusplan` is intentionally split across two layers:

Base resolution:
- resolves to default Sonnet

Runtime override:
- if the user-specified setting is exactly `opusplan`
- and current `permissionMode === 'plan'`
- and `exceeds200kTokens === false`
- then the runtime-effective model becomes default Opus

Equivalent decision shape:

```ts
if (
  getUserSpecifiedModelSetting() === 'opusplan' &&
  permissionMode === 'plan' &&
  !exceeds200kTokens
) {
  return getDefaultOpusModel()
}
return mainLoopModel
```

### Rewrite requirement
Preserve all three conditions for the Opus plan upgrade:
- explicit `opusplan` selection
- plan mode
- not past the 200k-token threshold

---

## 8.3 `haiku` is upgraded to Sonnet in plan mode
If the user-specified setting is exactly `haiku` and the runtime is in plan mode, the effective model becomes default Sonnet.

Equivalent decision shape:

```ts
if (getUserSpecifiedModelSetting() === 'haiku' && permissionMode === 'plan') {
  return getDefaultSonnetModel()
}
```

This is not the same as “every Haiku request becomes Sonnet.”
It is specifically a plan-mode rewrite.

### Rewrite requirement
Preserve plan-mode uplift for `haiku` to Sonnet.

---

## 8.4 Runtime switching depends on the original requested setting, not just the already-resolved concrete ID
The runtime checks `getUserSpecifiedModelSetting()` for values such as `opusplan` and `haiku`.

This matters because once aliases are fully resolved to concrete IDs, the special behavioral meaning would be lost.

### Rewrite requirement
Preserve access to the original configured model setting during runtime-effective selection.

---

## 9. Subagent model routing

## 9.1 Default subagent model is `inherit`
Subagents default to inheriting the parent thread model rather than independently resolving their own default family.

### Rewrite requirement
Preserve the subagent default as explicit semantic inheritance, not “pick whatever default model the system would use for a new session.”

---

## 9.2 Subagent model resolution priority
The inspected behavior is:

1. if `PINSER_SUBAGENT_MODEL` env var is set, it wins
2. else if the tool invocation specified a model, use that
3. else use agent-configured model or default subagent model (`inherit`)

### Rewrite requirement
Preserve this priority order.

Equivalent shape:

```ts
if (envSubagentModel) return parseUserSpecifiedModel(envSubagentModel)
if (toolSpecifiedModel) ...
const requestedAgentModel = agentModel ?? 'inherit'
...
```

---

## 9.3 `inherit` uses runtime-effective parent semantics
When the agent model is `inherit`, the system does not blindly reuse the raw parent configured setting.

Instead, it calls runtime model selection using:
- `permissionMode`
- parent model as current main model
- `exceeds200kTokens: false`

This ensures inherited subagents respect plan-mode runtime rewrites such as `opusplan` → Opus.

### Rewrite requirement
Preserve `inherit` as “inherit the parent’s effective runtime model semantics,” not merely “inherit the stored parent config string.”

---

## 9.4 Bare family aliases may inherit the parent’s exact concrete tier
If a subagent requests a bare family alias matching the parent model’s family, the runtime returns the parent’s exact concrete model string instead of re-resolving the alias against provider defaults.

Examples:
- parent is a concrete Opus 4.6 model on a third-party provider
- subagent asks for `opus`
- result is the exact parent concrete Opus model, not whatever `getDefaultOpusModel()` currently returns for that provider

This avoids surprising downgrades or version drift.

Equivalent family-match rule:

```ts
alias 'opus'   matches if canonical(parentModel) contains 'opus'
alias 'sonnet' matches if canonical(parentModel) contains 'sonnet'
alias 'haiku'  matches if canonical(parentModel) contains 'haiku'
```

Only bare aliases match.
Values like `opus[1m]`, `best`, and `opusplan` do not use this shortcut.

### Rewrite requirement
Preserve parent-tier inheritance for bare family aliases.

---

## 9.5 Tool-specified model outranks agent-configured model
If a tool invocation provides a model alias for the subagent, that value is used ahead of the agent’s configured model.

### Rewrite requirement
Preserve tool-specified subagent model override precedence.

---

## 9.6 Bedrock cross-region prefix is inherited by subagents
When the parent model uses a Bedrock cross-region prefix such as `eu.` or `us.`, alias-based subagent resolution inherits that prefix unless the child specification already explicitly includes its own region prefix.

This is required for correctness when IAM permissions or data residency are region-scoped.

Equivalent behavior shape:

```ts
const parentPrefix = getBedrockRegionPrefix(parentModel)
if (provider === 'bedrock' && parentPrefix exists) {
  if (child original spec already has region prefix) keep child as-is
  else prefix resolved child model with parentPrefix
}
```

### Rewrite requirement
Preserve Bedrock region-prefix inheritance for alias-resolved subagent models, while respecting explicitly prefixed child model strings.

---

## 10. Picker and option-generation behavior

## 10.1 The model picker is entitlement-aware, provider-aware, and fast-mode-aware
Picker options are not a static list.

They vary by:
- internal vs public user type
- Claude subscription tier
- Max / Team Premium vs other subscribers
- first-party vs third-party provider
- 1M access checks
- allowlist restrictions
- current fast-mode context for pricing text
- custom model env variables
- additional model options fetched during bootstrap

### Rewrite requirement
Preserve option generation as policy-based, not hardcoded UI constants.

---

## 10.2 The `Default` picker option is descriptive, not just null-valued
The `Default` option has:
- `value: null`
- user-tier-specific label/description text
- pricing metadata in some cases
- different description text for first-party vs third-party

### Rewrite requirement
Preserve `Default` as a first-class picker option with explanatory description, not merely an absence of selection.

---

## 10.3 Max and Team Premium defaults emphasize Opus
For Max and Team Premium subscribers:
- `Default` points conceptually to Opus
- Sonnet is shown as an alternative
- Haiku is shown as an alternative
- optional 1M entries appear based on access and merge behavior

### Rewrite requirement
Preserve premium-tier picker ordering and semantics rather than flattening all tiers into one list.

---

## 10.4 Standard subscribers default to Sonnet and show Opus as an alternative
For Pro / Team Standard / Enterprise-style subscriber cohorts:
- `Default` points conceptually to Sonnet
- Sonnet 1M may appear if allowed
- Opus or Opus 1M appears depending on merge rules and access
- Haiku is included

### Rewrite requirement
Preserve subscriber-tier-specific option composition.

---

## 10.5 PAYG first-party and PAYG third-party lists differ materially
For first-party PAYG, the list roughly includes:
- Default
- Sonnet 1M if available
- Opus or Opus 1M / merged variant depending on access
- Haiku

For third-party PAYG, the list may instead include:
- Default
- custom Sonnet if env-configured, else Sonnet 4.6 and maybe Sonnet 1M
- custom Opus if env-configured, else Opus 4.1, Opus 4.6, and maybe Opus 1M
- custom Haiku if env-configured, else provider-appropriate Haiku

### Rewrite requirement
Preserve materially different option sets for first-party vs third-party PAYG.

---

## 10.6 Unknown current model is appended to picker options
If the currently active model is not already present in the generated picker options, the UI appends a synthetic option:
- `value: currentModel`
- `label: modelDisplayString(currentModel)`
- `description: 'Current model'`

This prevents the current session state from disappearing from the picker.

### Rewrite requirement
Preserve explicit representation of the active model even when it is outside the standard picker catalog.

---

## 10.7 Additional/custom options are appended only if not already present
The runtime appends:
- `ANTHROPIC_CUSTOM_MODEL_OPTION`
- bootstrap-fetched additional model options
- current or initial custom model if missing

But only when their values are not already present.

### Rewrite requirement
Preserve dedup-by-value behavior when composing the final option list.

---

## 10.8 Allowlist filtering happens after composition and always preserves `Default`
When an allowlist exists, picker options are filtered so that:
- `value === null` is always preserved
- non-null entries survive only if allowed

### Rewrite requirement
Preserve special handling for the `Default` option during allowlist filtering.

---

## 11. 1M context access and merge behavior

## 11.1 `[1m]` is a suffix-level capability overlay, not a separate family
The runtime treats `[1m]` as a modifier layered onto an underlying family or explicit model string.

### Rewrite requirement
Preserve context-window suffixes as structured modifiers, not entirely separate family namespaces.

---

## 11.2 1M availability is gated by access checks
Sonnet and Opus 1M options only appear or validate under specific access checks.

The command layer also blocks setting unavailable 1M variants and returns targeted messages.

### Rewrite requirement
Preserve explicit access gating for 1M variants in both picker generation and command-time direct model setting.

---

## 11.3 Opus 1M “merge” changes both defaults and picker layout
There is a policy switch under which Opus default and Opus 1M are merged conceptually.

This affects:
- built-in default selection for some tiers
- picker entries
- fast-mode-related billing text

### Rewrite requirement
Preserve Opus-1M-merge as an explicit policy dimension rather than treating Opus and Opus 1M as always distinct.

---

## 11.4 Unknown subscriber state fails closed for Opus 1M merge
If a Claude subscriber exists but subscription type is unknown, the implementation disables Opus 1M merge to avoid surfacing options that the API might reject.

This is a defensive behavior against partially refreshed auth state.

### Rewrite requirement
Preserve fail-closed handling when entitlement state is ambiguous.

---

## 12. Direct `/model` command behavior

## 12.1 `/model` with no args opens picker; with args it performs direct set
The command has three user-facing modes:
- no args: open picker
- info args: show current model
- help args: show usage
- other args: treat as requested model and set directly

### Rewrite requirement
Preserve direct-set and picker-open as distinct paths.

---

## 12.2 `default` is a special direct-set token
When the direct-set command receives `default`, it is converted to `null` and stored as explicit default selection.

### Rewrite requirement
Preserve `default` as a command token meaning “clear explicit model back to built-in default.”

---

## 12.3 Known aliases bypass API validation
When the direct `/model X` path receives a recognized alias, the runtime accepts it without calling remote model validation.

Custom strings are validated remotely.

### Rewrite requirement
Preserve local acceptance for known aliases and remote validation only for non-alias custom model strings.

---

## 12.4 Direct-set path enforces allowlist and 1M access before validation
Before validating a custom model string, the command path checks:
- allowlist membership
- Opus 1M availability
- Sonnet 1M availability

### Rewrite requirement
Preserve pre-validation gating, especially because it changes user-facing errors and avoids pointless remote calls.

---

## 12.5 Showing current model distinguishes session override from base model
When a session-only effective model exists separately from the base main loop setting, the command output shows both:
- current model = session override
- base model = base setting

### Rewrite requirement
Preserve user-visible distinction between base model and session runtime override.

---

## 13. Validation and fallback suggestion behavior

## 13.1 Custom model validation uses a real API probe
Unknown/non-alias model strings are validated by making a minimal side query with:
- requested model
- `max_tokens: 1`
- no retries
- minimal `Hi` user message

This is not static regex validation.

### Rewrite requirement
Preserve remote capability validation for unknown custom model strings if compatibility with provider reality matters.

---

## 13.2 Alias and approved custom-option values are trusted locally
Validation short-circuits as successful for:
- known aliases
- allowlisted values
- the special `ANTHROPIC_CUSTOM_MODEL_OPTION` value
- previously cached successful validations

### Rewrite requirement
Preserve local trust fast-paths to avoid repeated network validation for known-good model values.

---

## 13.3 404s on third-party providers may include downgrade suggestions
For third-party providers, not-found errors for newer models may produce fallback suggestions such as:
- Opus 4.6 → suggest Opus 4.1
- Sonnet 4.6 → suggest Sonnet 4.5
- Sonnet 4.5 → suggest Sonnet 4

This is intentionally provider-sensitive and does not apply on first-party.

### Rewrite requirement
Preserve provider-aware fallback suggestion behavior for unavailable newer-version model IDs.

---

## 13.4 Validation errors are categorized, not generic
The validation path returns tailored user-visible errors for:
- empty model name
- allowlist rejection
- authentication failure
- network failure
- 404/not found
- generic API errors
- unknown errors

### Rewrite requirement
Preserve typed validation failures rather than collapsing everything into “invalid model.”

---

## 14. Marketing/display-name behavior

## 14.1 Public model display names are mapped from canonical IDs
Known public models are rendered to stable human-facing names like:
- `Opus 4.6`
- `Sonnet 4.6`
- `Haiku 4.5`
- variants with `(1M context)` suffixes where applicable

### Rewrite requirement
Preserve a dedicated canonical-ID-to-display-name mapping.

---

## 14.2 Unknown model strings may still get an upgrade hint in the picker
If a custom/current model is recognized as a known older family version, the option builder can show:
- a friendly label
- a description like `Newer version available · select Sonnet for Sonnet 4.6`

This is derived from family matching plus the currently configured family default.

### Rewrite requirement
Preserve family-aware upgrade hints for pinned older known models.

---

## 14.3 Foundry may have no reliable marketing-name mapping
For Foundry, deployment IDs are user-defined and may not imply an underlying model family.

The implementation therefore declines to infer a marketing name in some cases.

### Rewrite requirement
Preserve conservative omission of inferred friendly names when provider naming is user-controlled and ambiguous.

---

## 15. Fast mode interactions

## 15.1 Fast mode is only supported on a narrow model subset
Fast mode support is model-sensitive and currently tied to Opus 4.6-class models.

Equivalent support check shape:

```ts
isFastModeSupportedByModel(model) :=
  parseUserSpecifiedModel(modelOrDefault).toLowerCase().includes('opus-4-6')
```

### Rewrite requirement
Preserve fast-mode support as model-capability-dependent rather than as a global session toggle.

---

## 15.2 Switching to an incompatible model automatically turns fast mode off
When the user changes model and the new model does not support fast mode:
- fast mode runtime state is cleared/downgraded
- the user-facing success message notes `Fast mode OFF`
- this downgrade is automatic rather than treated as a separate explicit user preference change

### Rewrite requirement
Preserve automatic fast-mode downgrade on incompatible model selection.

---

## 15.3 Switching to a compatible model may preserve/show fast mode
If fast mode is enabled, available, and supported by the new model, model-change feedback reports `Fast mode ON`.

### Rewrite requirement
Preserve user-visible coupling between model changes and fast-mode state.

---

## 16. Suggested clean-room interfaces

A rewrite should expose interfaces roughly like:

```ts
type ModelSetting = string | null | undefined

type RuntimeModelContext = {
  permissionMode: 'default' | 'plan' | string
  mainLoopModel: string
  exceeds200kTokens: boolean
}

interface ModelPolicy {
  getUserSpecifiedModelSetting(): ModelSetting
  getDefaultMainLoopModelSetting(): string
  parseUserSpecifiedModel(setting: string): string
  getMainLoopModel(): string
  getRuntimeMainLoopModel(ctx: RuntimeModelContext): string
}

interface SubagentModelPolicy {
  getDefaultSubagentModel(): 'inherit'
  getAgentModel(params: {
    agentModel?: string
    parentModel: string
    toolSpecifiedModel?: string
    permissionMode?: string
  }): string
}

interface ModelOptionBuilder {
  getModelOptions(fastMode: boolean): Array<{
    value: string | null
    label: string
    description: string
    descriptionForModel?: string
  }>
}

interface ModelValidator {
  validateModel(model: string): Promise<
    | { valid: true }
    | { valid: false; error: string }
  >
}
```

---

## 17. Critical invariants to preserve

## 17.1 Original configured setting and resolved concrete model must both remain available
Failure mode:
- behavioral aliases like `opusplan` stop working correctly at runtime

## 17.2 Provider-specific defaults must be encapsulated in policy functions
Failure mode:
- 3P users get model IDs their provider does not actually support

## 17.3 Bare family alias on a subagent must be able to inherit exact parent tier
Failure mode:
- surprising downgrades/version drift inside multi-agent flows

## 17.4 Bedrock region prefix must survive subagent alias resolution
Failure mode:
- IAM/data-residency breakage for region-scoped inference profiles

## 17.5 Unknown custom model strings must preserve case
Failure mode:
- broken deployment IDs on case-sensitive third-party providers

## 17.6 Fast mode must not remain enabled on incompatible models
Failure mode:
- inconsistent UI state and invalid request behavior

## 17.7 Allowlist filtering must apply to configured values, not only the picker
Failure mode:
- startup/runtime can select models users can no longer choose interactively

## 17.8 `null` default selection must remain different from “no explicit setting exists”
Failure mode:
- inability to round-trip explicit user intent to return to default

---

## 18. Confidence and limits

High confidence:
- default selection by tier/provider, alias resolution, runtime plan-mode rewrites, subagent inheritance behavior, allowlist filtering, command behavior, validation mechanics, and fast-mode compatibility are directly grounded in inspected code

Moderate confidence:
- some entitlement/product framing around subscriber categories is synthesized from surrounding naming and picker logic rather than from every auth/bootstrap call site in this pass

That is acceptable here because this document is intended to preserve clean-room-compatible selection semantics, not to duplicate implementation text verbatim.
