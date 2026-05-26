# Permission engine for a clean-room rewrite

This document describes the runtime permission engine: the data model, rule model, mode model, evaluation pipeline, update/persistence semantics, and the most important invariants that a clean-room rewrite must preserve.

This is not a UI document. It focuses on the permission decision core and the contracts between:
- tools
- tool-specific permission checkers
- session/app state
- settings-backed rule persistence
- permission modes
- classifier-mediated approval flows
- headless/agent execution contexts

Companion docs:
- `docs/interfaces-and-endpoints.md`
- `docs/tool-contracts.md`
- `docs/bash-and-powershell-safety.md`
- `docs/implementation-notes-and-gotchas.md`

Primary inspected sources for this pass:
- `src/types/permissions.ts`
- `src/utils/permissions/permissions.ts`
- `src/utils/permissions/PermissionUpdate.ts`
- `src/utils/permissions/permissionSetup.ts`
- `src/utils/permissions/permissionsLoader.ts`
- `src/utils/permissions/permissionRuleParser.ts`
- `src/utils/permissions/PermissionMode.ts`
- plus tool-specific `checkPermissions(...)` implementations referenced indirectly

---

## 1. Purpose and architectural role

The permission engine answers one question repeatedly:

> Given a tool invocation, the current permission mode, the current rule set, and the current execution context, should the invocation be allowed, denied, or should the user be asked?

In this codebase, that question is not answered entirely by the tool and not entirely by the global permission system.

Instead, the architecture is layered:

1. global permission engine checks whole-tool rules and global mode effects
2. tool-specific permission logic checks content-sensitive rules and safety constraints
3. global engine applies mode-specific overrides and classifier/headless behavior
4. result is surfaced as allow / ask / deny

For a rewrite, preserving this split is important.

### Why the split matters
- some permissions are tool-agnostic (`allow Bash`, `deny WebFetch`)
- some permissions are content-sensitive and tool-specific (`Bash(git push:*)`, file path safety, sandbox asks)
- some behaviors are mode-dependent (`bypassPermissions`, `dontAsk`, `auto`, `plan`)
- some behaviors are environment-dependent (headless agents, Windows PowerShell sandbox policy)

A rewrite should not try to flatten all of this into one monolithic rule matcher.

---

## 2. Core data model

## 2.1 Permission behaviors
Three explicit rule/decision behaviors exist:

```ts
type PermissionBehavior = 'allow' | 'deny' | 'ask'
```

Semantics:
- `allow`: invocation may proceed without an interactive prompt
- `deny`: invocation must not proceed
- `ask`: invocation requires interactive approval, unless later transformed by mode/headless logic

### Rewrite requirement
Preserve all three behaviors explicitly. Do not collapse `ask` into either `allow` or `deny`.

---

## 2.2 Permission modes
Externally visible modes:

```ts
type ExternalPermissionMode =
  | 'acceptEdits'
  | 'bypassPermissions'
  | 'default'
  | 'dontAsk'
  | 'plan'
```

Internal/runtime modes add:

```ts
type PermissionMode = ExternalPermissionMode | 'auto' | 'bubble'
```

Observed active modes of practical importance here:
- `default`
- `acceptEdits`
- `bypassPermissions`
- `dontAsk`
- `plan`
- `auto`

### High-level semantics
- `default`: normal prompts and rule evaluation
- `acceptEdits`: permissive for certain safe edit operations, but not equivalent to bypass
- `bypassPermissions`: global allow mode, except for bypass-immune checks
- `dontAsk`: turns asks into denies
- `plan`: constrained mode with restoration semantics and special interaction with auto mode
- `auto`: classifier-mediated approval mode

### Rewrite requirement
Preserve mode identity distinctly. In particular:
- `acceptEdits` is not equivalent to `bypassPermissions`
- `dontAsk` is not equivalent to `bypassPermissions`
- `plan` is stateful, not just a label
- `auto` has separate gating and dangerous-rule stripping behavior

---

## 2.3 Permission rule value
Canonical structured form:

```ts
type PermissionRuleValue = {
  toolName: string
  ruleContent?: string
}
```

Interpretation:
- `toolName` selects the tool family
- `ruleContent` is tool-specific match content
- absence of `ruleContent` means a whole-tool rule

Examples:

```ts
{ toolName: 'Bash' }
{ toolName: 'Bash', ruleContent: 'git push:*' }
{ toolName: 'Read', ruleContent: '/project/**' }
{ toolName: 'Agent', ruleContent: 'Explore' }
```

### Rewrite requirement
Preserve the two-level rule shape:
- tool identity
- optional content payload interpreted by the tool subsystem

This is a central compatibility contract.

---

## 2.4 Permission rule object
Full rule shape:

```ts
type PermissionRule = {
  source: PermissionRuleSource
  ruleBehavior: PermissionBehavior
  ruleValue: PermissionRuleValue
}
```

Where source is one of:

```ts
type PermissionRuleSource =
  | 'userSettings'
  | 'projectSettings'
  | 'localSettings'
  | 'flagSettings'
  | 'policySettings'
  | 'cliArg'
  | 'command'
  | 'session'
```

### Meaning of source
Source is not metadata only. It matters for:
- precedence and diagnostics
- editability/persistence
- managed-policy restriction behavior
- UI explanation
- synchronization from disk

### Rewrite requirement
Preserve explicit source tagging on rules.

---

## 2.5 Tool permission context
The main runtime permission state is conceptually:

```ts
type ToolPermissionContext = {
  mode: PermissionMode
  additionalWorkingDirectories: Map<string, AdditionalWorkingDirectory>
  alwaysAllowRules: { [source]?: string[] }
  alwaysDenyRules: { [source]?: string[] }
  alwaysAskRules: { [source]?: string[] }
  isBypassPermissionsModeAvailable: boolean
  strippedDangerousRules?: { [source]?: string[] }
  shouldAvoidPermissionPrompts?: boolean
  awaitAutomatedChecksBeforeDialog?: boolean
  prePlanMode?: PermissionMode
  isAutoModeAvailable?: boolean // effectively present in classifier builds
}
```

Notes:
- the stored rule arrays are string forms, grouped by source and behavior
- additional working directories extend the effective filesystem permission scope
- `strippedDangerousRules` acts as a temporary stash when auto mode strips unsafe allow rules
- `prePlanMode` is used to restore mode after exiting plan mode
- `shouldAvoidPermissionPrompts` changes ask behavior in headless contexts

### Rewrite requirement
Preserve the split between:
- persisted rule definitions
- in-memory effective permission context
- transient mode-transition state (`prePlanMode`, `strippedDangerousRules`)

---

## 3. Rule string syntax and canonicalization

## 3.1 Canonical string format
Rules are serialized as either:

```text
ToolName
ToolName(ruleContent)
```

Examples:
- `Bash`
- `Bash(git status)`
- `Read(/project/**)`
- `Agent(Explore)`

### Important normalization behavior
The parser treats these as equivalent whole-tool rules:
- `Bash`
- `Bash()`
- `Bash(*)`

Likewise for other tools.

### Rewrite requirement
Preserve that normalization. Whole-tool rules must canonicalize to `{ toolName, ruleContent: undefined }`.

---

## 3.2 Escaping rules for ruleContent
Rule content may contain parentheses and backslashes. Serialization escapes them.

Canonical escaping behavior:
1. escape backslashes
2. escape `(`
3. escape `)`

Unescaping reverses that order.

### Rewrite requirement
Preserve lossless parse/serialize round-tripping for rule strings.

This matters because normalization is used for:
- deduplication
- deletion
- legacy-name migration
- comparison across settings reloads

---

## 3.3 Legacy tool name aliases
Rules are normalized through a legacy-name alias map.
Examples include mappings like:
- `Task` -> canonical agent tool
- `KillShell` -> canonical task-stop tool
- other legacy/renamed tool names

### Rewrite requirement
Preserve legacy alias normalization at parse time.

This is compatibility-critical because persisted rules and CLI arguments may still use old names.

---

## 4. Rule sources and persistence model

## 4.1 Editable vs non-editable sources
Editable sources:
- `userSettings`
- `projectSettings`
- `localSettings`

Non-editable / runtime-only / read-only sources:
- `policySettings`
- `flagSettings`
- `cliArg`
- `command`
- `session`

### Rewrite requirement
Preserve source editability distinctions.

In particular, rules from policy/flag/command sources must not be treated as user-editable persisted settings.

---

## 4.2 Managed-rules-only mode
If `allowManagedPermissionRulesOnly` is enabled in managed policy settings:
- only `policySettings` permission rules are respected when loading from disk
- “always allow” prompt options are suppressed
- attempts to persist new normal rules should fail/no-op

### Rewrite requirement
Preserve this as a hard policy gate, not merely a UI hint.

---

## 4.3 Loading rules from disk
Disk-backed permissions are loaded from enabled settings sources.

Normal behavior:
- load from all enabled settings sources
- convert settings JSON permissions arrays into `PermissionRule[]`

Managed-only behavior:
- load only from `policySettings`

### Rewrite requirement
Preserve full-source loading with managed-only override.

---

## 4.4 Lenient editing load
When appending rules to settings, the engine uses a lenient settings loader if strict validation fails.

Purpose:
- preserve unrelated malformed settings fields rather than losing permission edits
- avoid blocking permission rule updates because some unrelated settings area is invalid

### Rewrite requirement
Preserve the distinction between:
- strict validated settings for execution
- lenient parse-preserving settings access for editing/appending

This is subtle but important.

---

## 4.5 Sync-from-disk semantics
When syncing rules from disk into the in-memory permission context:
- disk-based source/behavior slots are cleared first
- then the newly loaded rules are applied as replacements

This prevents deleted disk rules from lingering in memory.

### Rewrite requirement
Preserve replacement semantics for disk sync.

Do not merely merge freshly loaded rules into the current in-memory context.

---

## 5. Permission updates

## 5.1 Update algebra
Permission updates are explicit structured operations:

```ts
type PermissionUpdate =
  | { type: 'addRules'; destination; rules; behavior }
  | { type: 'replaceRules'; destination; rules; behavior }
  | { type: 'removeRules'; destination; rules; behavior }
  | { type: 'setMode'; destination; mode }
  | { type: 'addDirectories'; destination; directories }
  | { type: 'removeDirectories'; destination; directories }
```

### Rewrite requirement
Preserve explicit update operations rather than mutating settings/context ad hoc.

---

## 5.2 Applying updates in memory
`applyPermissionUpdate(...)` mutates the logical permission context by:
- replacing mode
- appending/removing/replacing rule strings in behavior/source buckets
- adding/removing additional working directories

### Important semantic detail
`replaceRules` replaces all rules for one `(destination, behavior)` pair, not all rules globally.

### Rewrite requirement
Preserve update granularity at the level of:
- one behavior
- one destination/source

---

## 5.3 Persisting updates
Only updates whose destination is an editable settings source are persisted.
Others are runtime-only.

Persistable destinations:
- `userSettings`
- `projectSettings`
- `localSettings`

Non-persisted destinations:
- `session`
- `cliArg`

### Rewrite requirement
Preserve runtime-only destinations.

---

## 5.4 Directory additions as permission context changes
Additional working directories are separate from ordinary tool rules.
They expand the trusted/accessible workspace scope.

They are represented as:

```ts
type AdditionalWorkingDirectory = {
  path: string
  source: WorkingDirectorySource
}
```

### Rewrite requirement
Preserve directory additions as first-class permission state, not as fake file-read rules.

---

## 6. Decision result model

## 6.1 PermissionDecision
Core decision union:

```ts
type PermissionDecision =
  | { behavior: 'allow', ... }
  | { behavior: 'ask', ... }
  | { behavior: 'deny', ... }
```

## 6.2 PermissionResult
Tool-level permission checkers may additionally return:

```ts
{ behavior: 'passthrough', ... }
```

Meaning:
- tool-specific checker did not conclusively allow/ask/deny
- global engine should convert it to an ask later if still unresolved

### Rewrite requirement
Preserve `passthrough` as an internal intermediate result.

This is important because tool-level checkers are not always the final authority.

---

## 6.3 Ask result structure
Ask decisions can include:
- `message`
- `updatedInput`
- `decisionReason`
- `suggestions`
- `blockedPath`
- `metadata`
- `pendingClassifierCheck`
- optional content blocks

### Important implication
An ask decision is not just “show a prompt.” It can also:
- carry a transformed input
- carry suggested permanent/session rule updates
- carry explanation metadata for UI
- request asynchronous classifier help

### Rewrite requirement
Preserve the rich ask payload shape.

---

## 6.4 Allow result structure
Allow decisions can include:
- `updatedInput`
- `userModified`
- `decisionReason`
- `toolUseID`
- `acceptFeedback`
- content blocks

### Rewrite requirement
Preserve `updatedInput` on allow results.
Tool permission code can sanitize or rewrite the invocation.

---

## 6.5 Deny result structure
Deny decisions include:
- `message`
- `decisionReason`
- optional `toolUseID`

### Rewrite requirement
Preserve explicit deny messages and decision reasons for transcript/debug/UI fidelity.

---

## 7. Decision reason model

The engine attaches machine-readable reasons to permission outcomes.
This is an important interface.

Key reason variants include:
- `rule`
- `mode`
- `subcommandResults`
- `permissionPromptTool`
- `hook`
- `asyncAgent`
- `sandboxOverride`
- `classifier`
- `workingDir`
- `safetyCheck`
- `other`

### Why this matters
Decision reasons drive:
- prompt messages
- analytics
- UI explanations
- special-case transformations
- debugging and auditability

### Rewrite requirement
Preserve a structured reason union rather than string-only explanations.

Especially important variants:
- `rule`, because rule source/behavior/value matter
- `mode`, because mode transformations are visible behavior
- `safetyCheck`, because some are bypass-immune and classifier-non-approvable
- `classifier`, because auto-mode logic and analytics depend on it
- `subcommandResults`, because shell compound-command prompting depends on it

---

## 8. Whole-tool rule matching

## 8.1 Tool-wide matching
A whole-tool rule is a rule with no `ruleContent`.
It matches an entire tool, not a content-specific invocation.

Examples:
- `Bash`
- `WebFetch`
- `mcp__serverName`

### Matching behavior
A whole-tool rule does not match if it has content.
Only rules with undefined content are treated as whole-tool rules.

### Rewrite requirement
Preserve strict separation between:
- whole-tool rules
- content-sensitive rules

---

## 8.2 MCP server-level matching
Whole-tool rule matching includes MCP server grouping semantics.
A rule for an MCP server can match tools under that server.

Examples of intended semantics:
- a rule like `mcp__server1` matches all tools from that server
- wildcard server-level patterns like `mcp__server1__*` also act server-wide

### Rewrite requirement
Preserve MCP-aware matching distinct from builtin tool matching.

---

## 9. High-level permission pipeline

At runtime, the global engine function behaves roughly as follows.

## 9.1 Step 1: whole-tool deny
If the entire tool is denied by rule, return deny.

## 9.2 Step 2: whole-tool ask
If the entire tool has an ask rule, return ask unless a narrow Bash sandbox auto-allow exception applies.

## 9.3 Step 3: tool-specific permission check
Call `tool.checkPermissions(parsedInput, context)`.
This may return:
- allow
- ask
- deny
- passthrough

## 9.4 Step 4: enforce tool-level deny and bypass-immune asks
Global engine respects tool-level:
- deny
- content-specific ask rules
- safety-check asks
- user-interaction-required asks

These survive even before global mode handling.

## 9.5 Step 5: apply bypassPermissions / plan-with-bypass semantics
If current mode implies bypass is active, return allow unless the invocation was already caught by bypass-immune checks.

## 9.6 Step 6: whole-tool allow
If the entire tool is allowed by rule, return allow.

## 9.7 Step 7: convert passthrough to ask
If tool-specific logic returned `passthrough`, convert it into `ask` with a generated message.

## 9.8 Step 8: post-processing of ask
If result is ask, then higher-level transformations may apply:
- `dontAsk` converts ask to deny
- `auto` may run classifier and convert ask to allow/deny
- headless/async-agent mode may auto-deny after hooks
- denial tracking may force fallback prompting behavior

### Rewrite requirement
Preserve the layered nature of this pipeline.

A rewrite should not let whole-tool allow rules or bypass mode erase bypass-immune safety checks.

---

## 10. The most important precedence rules

## 10.1 Deny beats everything earlier than allow
If a whole-tool deny matches, that is terminal.
If a tool-specific deny fires, that is terminal unless a higher-level fatal/abort path exists.

## 10.2 Content-specific ask can beat bypass
Tool-specific ask results tagged as explicit ask rules are respected even in bypass mode.

## 10.3 Safety-check ask can beat bypass
Safety checks are explicitly bypass-immune.

## 10.4 Whole-tool allow happens after bypass-immune asks
This ordering matters.

## 10.5 `dontAsk` applies at the end of ask production
`dontAsk` does not change allow or deny directly; it transforms final asks into denies.

### Rewrite requirement
Preserve these precedence rules exactly in effect, even if implementation structure differs.

---

## 11. Bypass-immune categories

Two particularly important categories are intentionally not bypassed by `bypassPermissions`:

## 11.1 Content-specific ask rules
Examples:
- `Bash(npm publish:*)` forcing approval for publish-like commands

These arise from tool-specific permission checking rather than whole-tool ask matching.

## 11.2 Safety checks
Examples called out in code/comments include sensitive paths like:
- `.git/`
- `.pinser/`
- `.vscode/`
- shell config files

These are represented with reason type:

```ts
{ type: 'safetyCheck', reason: string, classifierApprovable: boolean }
```

### Rewrite requirement
Preserve both categories as bypass-immune.

This is one of the most important invariants in the permission engine.

---

## 12. Permission prompt messages

The engine synthesizes prompt messages from structured reasons.

Notable cases:
- classifier reason -> classifier-specific explanation
- hook reason -> identifies hook
- rule reason -> identifies rule and source
- subcommandResults -> names the subcommands requiring approval
- sandboxOverride -> “Run outside of the sandbox”
- mode reason -> explains current mode

### Rewrite requirement
Preserve reason-sensitive prompt generation.

A generic “permission required” message is not behaviorally equivalent.

---

## 13. Auto mode and classifier interaction

## 13.1 Auto mode is not bypass mode
Auto mode starts from an `ask` and attempts to replace interactive approval with classifier approval.

That means:
- normal permission logic still runs first
- bypass-immune safety asks still matter
- some asks never go to classifier

### Rewrite requirement
Preserve auto mode as a post-ask transformation, not a pre-check global allow mode.

---

## 13.2 Auto-mode preconditions
Auto-mode classifier path only runs when:
- classifier feature/build is present
- mode is `auto`, or plan mode with auto active
- result is currently `ask`
- tool is not in certain excluded categories
- the ask is classifier-approvable

### Rewrite requirement
Preserve classifier entry conditions as narrow and explicit.

---

## 13.3 Classifier-non-approvable safety checks
If decision reason is:

```ts
{ type: 'safetyCheck', classifierApprovable: false }
```

then auto mode must not auto-approve it.

Behavior:
- if interactive prompting is available, remain ask
- if prompts are unavailable, deny in async/headless mode

### Rewrite requirement
Preserve `classifierApprovable` as a first-class gate.

---

## 13.4 Accept-edits fast path inside auto mode
Before calling the classifier, the engine may test whether the action would be allowed under `acceptEdits` mode.
If yes, it skips the classifier and allows.

Excluded from this fast path:
- Agent tool
- REPL tool

Rationale in code/comments:
- Agent and REPL can hide more dangerous semantics than ordinary edit-like tools

### Rewrite requirement
Preserve this optimization and its exclusions.

---

## 13.5 Safe-tool allowlist inside auto mode
Some tools are on a safe allowlist for auto mode and can bypass classifier evaluation.

### Rewrite requirement
Preserve existence of a separate auto-mode safe-tool allowlist.
It is distinct from ordinary permission rules.

---

## 13.6 Dangerous allow rules are stripped in auto mode
When entering auto mode, dangerous allow rules are removed from the active in-memory context and stashed in `strippedDangerousRules`.

This prevents rules like:
- `Bash(*)`
- `Bash(python:*)`
- dangerous PowerShell execution patterns
- `Agent(*)`

from bypassing the classifier entirely.

When leaving auto mode, these stripped rules are restored.

### Rewrite requirement
Preserve:
- stripping on auto entry
- restoration on auto exit
- stash of the exact stripped rules

This is a major clean-room requirement.

---

## 13.7 Dangerous rule detection is broader than just whole-tool shell allow
Dangerous auto-bypass rules include:
- whole-tool Bash allow
- script interpreter Bash prefixes/wildcards
- dangerous PowerShell execution prefixes/wildcards
- agent/sub-agent allow rules
- some tmux-related rules in ant-only builds

### Rewrite requirement
Preserve dangerous-rule detection as semantic, not purely syntactic.

---

## 13.8 Denial tracking in auto mode
Auto mode tracks:
- consecutive denials
- total denials

Successful tool use resets the consecutive denial streak.

If denial limits are exceeded:
- interactive mode falls back to prompting so the user can review
- headless mode aborts the agent

### Rewrite requirement
Preserve denial tracking and fallback behavior.

This is important both for UX and for preventing classifier-driven dead loops.

---

## 13.9 Classifier unavailable behavior
If classifier is unavailable:
- in fail-closed mode, deny with retry guidance
- in fail-open mode, fall back to ordinary permission handling

If transcript is too long for classifier:
- do not retry classifier as if it were transient
- fall back to manual prompting if possible
- abort in headless mode

### Rewrite requirement
Preserve these degraded-mode semantics.

---

## 14. Headless / async agent behavior

## 14.1 `shouldAvoidPermissionPrompts`
When permission prompts are unavailable, ask results cannot simply remain asks.

Behavior:
1. if auto mode classifier can resolve, it may do so first
2. otherwise run PermissionRequest hooks for headless agents
3. if hook makes no decision, auto-deny

### Rewrite requirement
Preserve headless execution as a distinct permission environment.

---

## 14.2 Headless PermissionRequest hooks
Hooks may still allow or deny when no UI prompt can be shown.

If a hook:
- allows: optional permission updates may be persisted and applied
- denies: tool use is denied, optional interrupt may abort the controller
- does nothing: engine falls back to auto-deny

### Rewrite requirement
Preserve hook-before-auto-deny ordering for headless asks.

---

## 15. Tool-specific permission delegation contract

Each tool exposes a `checkPermissions(parsedInput, context)`-style method that returns a `PermissionResult`.

This is a critical interface.

## 15.1 Expected semantics
A tool-specific checker is allowed to:
- return `allow`
- return `deny`
- return `ask`
- return `passthrough`
- supply `updatedInput`
- supply suggestions for rules/directories/mode updates
- attach structured `decisionReason`

### Rewrite requirement
Preserve tool-specific permission logic as a plugin/delegation point.

---

## 15.2 Tool checker is not the whole engine
The global engine still applies after tool checker returns.
For example:
- `passthrough` becomes `ask`
- `dontAsk` may convert ask to deny
- auto mode may convert ask to allow/deny
- headless mode may convert ask to deny
- whole-tool allow may allow before prompt generation if earlier conditions permit

### Rewrite requirement
Do not move all final semantics into the tool checker.

---

## 16. Plan mode interaction

## 16.1 `prePlanMode`
Entering `plan` stores the prior mode in `prePlanMode` so exiting plan can restore it.

### Rewrite requirement
Preserve plan mode as a transition with restoration metadata.

---

## 16.2 Plan mode and auto mode
Plan mode can sometimes run with auto-mode semantics active, depending on settings/gates.

Important behaviors:
- entering plan from auto may keep auto semantics active or deactivate them, depending on configuration
- entering plan from non-bypass mode may activate auto semantics in plan when configured
- dangerous rules may therefore need stripping during plan mode too
- leaving plan must restore stripped rules appropriately

### Rewrite requirement
Preserve plan/auto interaction as explicit transition logic, not as independent booleans.

---

## 16.3 Plan mode with bypass availability
In some situations, plan mode inherits bypass-permissions effective allowance because the user originally started from bypass mode.

This is represented using `isBypassPermissionsModeAvailable` rather than plan itself meaning bypass.

### Rewrite requirement
Preserve this nuance.

---

## 17. Initialization and mode entry

## 17.1 Initial permission mode derivation
Initial mode is chosen from several inputs in priority order:
- dangerous skip permissions flag
- explicit CLI permission mode
- settings default mode
- fallback default

But gates/settings may disable some modes, especially:
- `bypassPermissions`
- `auto`

### Rewrite requirement
Preserve ordered mode selection plus gate enforcement.

---

## 17.2 Base tools CLI and implicit denies
If a base tool set is explicitly configured, tools not in that set are implicitly denied by adding them to CLI disallowed tools.

### Rewrite requirement
Preserve base-tool restriction as explicit deny expansion, not as a separate ad hoc code path later.

---

## 17.3 Initial tool permission context construction
Initialization combines:
- CLI allow rules
- CLI deny rules
- disk-loaded rules
- additional working directories
- mode availability flags
- auto-mode dangerous-rule detection outputs

### Rewrite requirement
Preserve initialization as a composition step that builds one effective context object.

---

## 18. Additional working directories

## 18.1 Purpose
Additional working directories expand what the engine considers within permitted workspace scope.

They are used by path-sensitive tools and permission prompts.

## 18.2 Validation and source tracking
Added directories are validated and stored with source metadata.

### Rewrite requirement
Preserve directory validation before acceptance and preserve source tagging.

---

## 19. Important invariants for a rewrite

## 19.1 Whole-tool allow must not erase bypass-immune safety asks
Failure mode:
- sensitive file or dangerous shell action gets silently allowed because a broad allow rule exists

## 19.2 `passthrough` is not allow
Failure mode:
- tool checker returns neutral result and action runs without prompting

## 19.3 `dontAsk` transforms ask -> deny only after normal permission evaluation
Failure mode:
- bypass-immune denies/asks and tool-level rewrites become inconsistent

## 19.4 Auto mode must strip dangerous pre-allow rules
Failure mode:
- classifier is silently bypassed by broad shell/agent allow rules

## 19.5 Disk sync must clear stale source buckets before replacing
Failure mode:
- deleted settings rules continue to apply until restart

## 19.6 Rule normalization must be canonical for dedupe and deletion
Failure mode:
- `Bash`, `Bash()`, and `Bash(*)` drift apart and cannot be managed consistently

## 19.7 Headless asks must not hang indefinitely
Failure mode:
- background/sub-agent execution stalls waiting for impossible UI interaction

## 19.8 Rule source matters
Failure mode:
- managed policy rules become editable or session/CLI rules are incorrectly persisted

## 19.9 Plan mode must preserve restoration state
Failure mode:
- exiting plan lands in the wrong mode or leaves dangerous-rule stripping stuck on/off

## 19.10 Decision reasons are part of the interface
Failure mode:
- explanation/UI/analytics/debug behavior regresses even if raw allow/deny outcomes mostly work

---

## 20. Minimal implementation shape for a rewrite

A compatible rewrite should expose something structurally like:

```ts
type PermissionEngine = {
  hasPermissionsToUseTool(
    tool: Tool,
    input: Record<string, unknown>,
    context: ToolUseContext,
    assistantMessage: AssistantMessage,
    toolUseID: string,
  ): Promise<PermissionDecision>

  checkRuleBasedPermissions(
    tool: Tool,
    input: Record<string, unknown>,
    context: ToolUseContext,
  ): Promise<PermissionAskDecision | PermissionDenyDecision | null>

  applyPermissionUpdate(
    context: ToolPermissionContext,
    update: PermissionUpdate,
  ): ToolPermissionContext

  applyPermissionUpdates(
    context: ToolPermissionContext,
    updates: PermissionUpdate[],
  ): ToolPermissionContext

  persistPermissionUpdate(update: PermissionUpdate): void
  persistPermissionUpdates(updates: PermissionUpdate[]): void

  loadAllPermissionRulesFromDisk(): PermissionRule[]
  syncPermissionRulesFromDisk(
    context: ToolPermissionContext,
    rules: PermissionRule[],
  ): ToolPermissionContext

  transitionPermissionMode(
    fromMode: PermissionMode,
    toMode: PermissionMode,
    context: ToolPermissionContext,
  ): ToolPermissionContext
}
```

This exact symbol set is not mandatory, but the behavioral surface is.

---

## 21. Clean-room guidance: what to preserve vs what can vary

## Preserve closely
- rule data model
- update algebra
- source model
- whole-tool vs content-specific split
- permission result/decision shapes
- precedence rules
- bypass-immune ask categories
- auto-mode dangerous-rule stripping/restoration
- headless hook-before-deny flow
- plan-mode restoration semantics

## Can vary somewhat
- exact internal function boundaries
- exact analytics/logging call sites
- exact message wording, if meaning is preserved
- exact in-memory collection types, if semantics remain equivalent
- exact organization of tool-specific permission helper modules

---

## 22. Confidence and limits

High confidence:
- the decision model, rule model, source model, update model, and mode transitions described here are directly supported by inspected code
- the bypass-immune and auto-mode dangerous-rule-stripping behaviors are clearly intentional and central

Lower confidence:
- this document does not enumerate every tool-specific permission checker’s internal matching logic
- some classifier/feature-gate details are build- or environment-dependent

Still, this document should be sufficient as the architectural and compatibility contract for re-implementing the permission engine itself.