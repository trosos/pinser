# Bash and PowerShell safety model for a clean-room rewrite

This document describes the shell-tool safety model that should be preserved in a clean-room rewrite.

It is intended to be implementation-enabling, not merely descriptive. A rewrite team should be able to infer the essential decision logic, safety invariants, and compatibility-sensitive behavior from this document without consulting the original code.

This document complements:
- `docs/tool-contracts.md`
- `docs/interfaces-and-endpoints.md`
- `docs/implementation-notes-and-gotchas.md`
- `docs/permission-engine.md`

Primary inspected sources for this pass:
- `src/tools/BashTool/BashTool.tsx`
- `src/tools/BashTool/bashPermissions.ts`
- `src/tools/BashTool/readOnlyValidation.ts`
- `src/tools/BashTool/shouldUseSandbox.ts`
- `src/utils/sandbox/sandbox-adapter.ts`
- `src/utils/permissions/permissions.ts`
- `src/tools/PowerShellTool/PowerShellTool.tsx`
- `src/tools/PowerShellTool/powershellPermissions.ts`
- `src/tools/PowerShellTool/readOnlyValidation.ts`

---

## 1. Scope and goals

The shell safety system is not one mechanism. It is the composition of:
- permission rules
- parser-/validator-based safety checks
- read-only auto-allow logic
- sandbox routing
- backgrounding behavior
- transcript/result shaping
- platform-specific hardening

For rewrite purposes, the most important takeaway is:

> Shell execution is not approved by a single “safe/unsafe” boolean. It is approved by an ordered pipeline of checks, some of which are deny-capable, some ask-capable, some allow-capable, and some only affect execution mode.

A rewrite should preserve that structure.

---

## 2. Common concepts across Bash and PowerShell

## 2.1 Shell tools support explicit background execution
Both shell tools support:
- foreground execution
- explicit background execution (`run_in_background: true`)
- automatic backgrounding of long-running commands in certain contexts
- user-initiated backgrounding of running foreground commands

This is operational behavior, not only UI behavior.

### Compatibility requirement
A rewrite should preserve:
- stable background-task identifiers
- persisted output paths for background tasks
- different provenance labels for:
  - explicitly backgrounded by the model
  - manually backgrounded by the user
  - auto-backgrounded by assistant-mode responsiveness logic

---

## 2.2 Shell tools expose an explicit unsafe sandbox override
Both tools support input shaped like:

```ts
{
  command: string
  timeout?: number
  run_in_background?: boolean
  dangerouslyDisableSandbox?: boolean
}
```

For Bash, this field actively participates in per-command sandbox routing.
For PowerShell, it is also present and forwarded to sandbox-routing logic, but native Windows policy can supersede it because native Windows sandboxing is unavailable.

### Compatibility requirement
A rewrite should preserve:
- the existence of `dangerouslyDisableSandbox`
- policy ability to disallow using it
- clear user/model semantics that sandbox bypass is exceptional

---

## 2.3 Read-only auto-allow exists, but only after significant filtering
Both tools implement a class of commands that can execute without an interactive prompt when they are sufficiently proven read-only.

This is not a simple allowlist of program names.
It depends on:
- command parsing
- flag validation
- dangerous-pattern detection
- path safety
- compound-command structure
- platform rules
- git-specific hardening

### Compatibility requirement
A rewrite should preserve read-only auto-allow as a structured decision, not as a superficial list of binaries/cmdlets.

---

## 2.4 Deny rules must be harder to bypass than allow rules
A recurring design principle in the shell code is:
- allow rules are conservative
- deny rules are aggressively normalized so prefix tricks do not bypass them

Examples include:
- stripping more env-var prefixes for deny/ask matching than for allow matching
- canonicalizing aliases/cmdlet names for PowerShell deny matching
- checking subcommands individually in compound commands

### Compatibility requirement
A rewrite should preserve the asymmetry:
- **deny/ask matching may intentionally over-match a little for safety**
- **allow matching must not over-match**

---

## 3. Bash safety model

## 3.1 Bash permission pipeline
At a high level, Bash permission evaluation proceeds as follows:

1. tool-level deny rules
2. tool-level ask rules
3. Bash-specific command permission checks
4. safety-check / path-check / sed-check / command-structure checks
5. mode-specific allow logic
6. read-only auto-allow
7. sandbox auto-allow when enabled
8. prompt/passthrough if still unresolved

A more accurate rewrite-oriented model is below.

---

## 3.2 Bash rule matching semantics
Bash permission rules support three effective match forms:

1. **exact**
   - matches one command string exactly
2. **prefix**
   - matches a command prefix plus either end-of-string or a following space
3. **wildcard**
   - shell-style wildcard matching over a single subcommand string

Examples of intended semantics:

```text
Bash(git status)      -> exact
Bash(git commit:*)    -> prefix-like command family
Bash(*npm*test*)      -> wildcard
```

### Important behavior
Prefix/wildcard allow rules must not match compound commands as whole strings when that would allow extra operations to piggyback behind an allowed prefix.

Example of behavior to preserve:
- `Bash(cd:*)` must **not** allow `cd dir && rm -rf /`

### Compatibility requirement
A rewrite should:
- split compound Bash commands before applying prefix/wildcard allow logic
- still allow deny/ask logic to inspect all relevant subcommands
- preserve word-boundary behavior for prefix matching

---

## 3.3 Bash normalization used for rule matching
Bash rule matching does not compare the raw command only.
It also uses normalization passes.

### 3.3.1 Safe-wrapper stripping
For permission matching, Bash may strip leading wrapper commands such as:
- `timeout`
- `time`
- `nice`
- `stdbuf`
- `nohup`

This is done so rules for the underlying command still match.

Example intended behavior:
- allow/deny rule for `npm install:*` should still see through `timeout 30 npm install ...`

### 3.3.2 Safe env-var stripping
Some leading env var assignments are stripped for matching if they are considered safe.
These are carefully allowlisted.
Examples include benign execution-context variables, locale vars, selected tool config vars, etc.

### 3.3.3 Aggressive env-var stripping for deny/ask matching
For deny/ask behavior, Bash can strip **all** leading env-var assignments using a broader parser, because denied commands should stay denied even when prefixed with arbitrary `FOO=bar` syntax.

### Compatibility requirement
A rewrite should preserve three separate concepts:
- safe-wrapper stripping
- safe env-var stripping for ordinary matching
- aggressive env-var stripping for deny/ask hardening

Do not collapse these into one generic normalization step.

---

## 3.4 Bash excluded-commands and sandbox routing
Bash sandbox routing is decided per invocation by `shouldUseSandbox(...)`.

A command uses sandbox iff all of the following are true:
- global sandboxing is enabled and available
- a command string exists
- `dangerouslyDisableSandbox` is not both set and policy-permitted
- command does not match excluded-command routing rules

### Excluded-command matching
Excluded commands are matched against:
- dynamic config-disabled commands/substrings in some builds
- user-configured sandbox excluded commands in settings

Matching considers:
- compound command splitting
- wrapper/env-var stripping candidates
- exact/prefix/wildcard command-family matching

### Important note
Excluded commands are explicitly documented in code as a **convenience feature, not the primary security boundary**.

### Compatibility requirement
A rewrite should preserve:
- per-command sandbox routing
- excluded-command matching as convenience behavior
- the architectural distinction that permission/sandbox enforcement is the real security boundary

---

## 3.5 Bash sandbox auto-allow
When all of the following are true:
- sandboxing is enabled
- `autoAllowBashIfSandboxed` is enabled
- this invocation will actually run sandboxed

then Bash may auto-allow execution **unless** explicit deny/ask rules still require blocking/prompting.

### Critical nuance
Sandbox auto-allow does **not** ignore explicit deny/ask rules.
For compound commands, it must inspect subcommands too, because a full compound string may not start with the denied subcommand.

Example invariant:
- `echo ok && rm -rf x` must not be auto-allowed merely because the full command doesn’t start with `rm`

### Compatibility requirement
A rewrite should preserve:
- sandbox auto-allow as a distinct fast path
- explicit deny/ask precedence over sandbox auto-allow
- subcommand inspection for compound commands in sandbox auto-allow mode

---

## 3.6 Bash AST-first parsing and fallback
Bash uses an AST-based parse/security path when available, with a legacy fallback path when not available.

### Intended model
1. attempt structural parse
2. if parse says “simple and analyzable”, use AST-derived subcommands/redirects
3. if parse says “too complex”, prompt unless deny rules already block
4. if parser unavailable, use older fallback parsing and safety heuristics

### What “too complex” means operationally
This includes commands whose structure cannot be safely reasoned about for auto-allow purposes, such as:
- substitutions
- structural tricks
- parse-differential edge cases
- complex shell control flow

### Compatibility requirement
A rewrite should preserve the state distinction:
- parse succeeded and is structurally safe to reason about
- parse succeeded but is too complex for static approval
- parse unavailable / degraded

This distinction drives whether read-only/auto-allow logic may run.

---

## 3.7 Bash compound-command handling
Bash explicitly splits compound commands and evaluates them piecewise.
This is security-critical.

It exists to prevent cases where one allowed/read-only command masks another dangerous command.

### Examples of preserved behavior
- `ls && rm file` is not read-only
- `cat file | grep x` can still be classified as read/search
- `cd dir && git status` triggers a special prompt path
- any denied subcommand denies the overall compound command

### Compatibility requirement
A rewrite should preserve:
- subcommand-aware deny matching
- subcommand-aware ask matching
- compound-level aggregation of decisions
- denial precedence over per-subcommand asks/allows

---

## 3.8 Bash command-injection / unsafe-pattern checks
Bash has a separate safety layer for commands that may parse in suspicious or dangerous ways.

This catches patterns such as:
- command-substitution style behavior
- malformed constructs
- misparsing-prone syntax
- dangerous heredoc/substitution interactions
- hidden operators/redirection issues in legacy paths

### Compatibility requirement
A rewrite should preserve a distinct “structural safety” layer, separate from rule matching and separate from read-only classification.

A command may be:
- allowed by rule shape
- yet still require approval because its syntax is injection-prone or too complex

---

## 3.9 Bash path validation and redirection validation
Bash has dedicated path validation for command arguments and output redirections.

### Important behaviors
- redirections on the original command must be validated, even if subcommand splitting strips them away for other checks
- dangerous paths can trigger deny or ask
- path checks happen early enough that writes outside approved areas do not bypass policy
- compound `cd` context affects path safety reasoning

### Compatibility requirement
A rewrite should preserve:
- separate validation of redirected output targets
- path validation on both subcommand arguments and original-command redirections
- path validation that is sensitive to compound-command structure

---

## 3.10 Bash `cd` + `git` special-case guard
Bash explicitly prompts for compound commands containing both:
- a directory-changing command (`cd`, `pushd`, `popd`)
- and a git command

### Rationale
This mitigates bare-repository / hook-execution attacks where changing directory first alters the repository context in which git executes.

### Compatibility requirement
A rewrite should preserve this as a dedicated guard, not assume generic read-only classification is sufficient.

---

## 3.11 Bash bare-repo and git-internal-path hardening
Bash read-only/safety logic includes several git-specific hardening behaviors.

### 3.11.1 Bare-repo detection
If cwd looks like a bare or exploited git repository, git commands should not auto-allow.

### 3.11.2 Creating git-internal files before running git
A compound command that writes paths like:
- `HEAD`
- `objects/...`
- `refs/...`
- `hooks/...`

and then runs git must require approval.

### Compatibility requirement
A rewrite should preserve both:
- cwd bare-repo detection
- compound-command detection of git-internal-file planting before git execution

---

## 3.12 Bash read-only classification
Bash read-only auto-allow is based on a mix of:
- exact command allowlists
- declarative flag validation tables
- regex constraints
- custom dangerous-command callbacks
- compound-command structure restrictions
- UNC/network-path protections
- git-specific safety exceptions

### Important non-obvious rules
- parsing failure means not read-only
- unquoted expansions/globs may make a command not read-only
- some apparently harmless tools are excluded because certain flags can write, execute code, or make network requests
- allowlisted commands still reject dangerous flags/positionals

### Compatibility requirement
A rewrite should preserve read-only classification as **argument-sensitive**, not command-name-only.

---

## 3.13 Bash backgrounding behavior
Bash supports:
- explicit backgrounding by input flag
- timeout-driven backgrounding for eligible commands
- assistant-mode auto-backgrounding after a blocking budget
- user-driven backgrounding of a foreground task

### Important invariant
Some commands are intentionally disallowed from auto-backgrounding, notably sleep-style waiting commands.

### Compatibility requirement
A rewrite should preserve:
- explicit vs automatic backgrounding distinction
- command-specific auto-background exclusions
- continuity of task IDs and output paths when a foreground task is converted in place to background

---

## 4. PowerShell safety model

## 4.1 PowerShell permission pipeline
PowerShell permissioning follows a similar but not identical structure:

1. exact deny/ask/allow rules
2. prefix/wildcard deny/ask rules
3. parser and security checks
4. per-subcommand rule checks over parsed command elements
5. git/path/provider/UNC/cd-specific special-case checks
6. exact-allow and read-only/allowlist logic
7. mode-specific allow logic
8. passthrough/prompt if unresolved

A key difference from Bash is that PowerShell explicitly adopts a **collect-then-reduce** model for many post-parse decisions, so later deny decisions cannot be masked by earlier ask decisions.

### Compatibility requirement
A rewrite should preserve the effective precedence:
- deny > ask > allow > passthrough

And, ideally, preserve a collect-then-reduce structure rather than relying on many ad hoc early returns.

---

## 4.2 PowerShell rule matching semantics
PowerShell rules conceptually support the same three match families:
- exact
- prefix
- wildcard

But matching is **case-insensitive**.

### Additional PowerShell-specific behavior
Rule matching canonicalizes command names through aliases/canonical cmdlets.
This means rules written for aliases and rules written for canonical cmdlets should cross-match.

Examples of intended behavior:
- deny `Remove-Item:*` also blocks `rm ...`
- deny `rm *` also blocks `Remove-Item ...`

### Compatibility requirement
A rewrite should preserve:
- case-insensitive matching
- alias/canonical cross-matching
- careful asymmetry where allow matching does not over-broaden in unsafe ways

---

## 4.3 PowerShell module-prefix and canonicalization behavior
PowerShell strips cmdlet/module qualification for many matching/canonicalization flows, but does so more conservatively for allow behavior than for deny/ask behavior.

### Rationale
This helps:
- deny rules continue to block aliased/module-qualified variants
- while allow rules avoid over-broad matches across unrelated module-qualified commands

### Compatibility requirement
A rewrite should preserve this asymmetry.
Do not blindly canonicalize everything the same way for allow and deny.

---

## 4.4 PowerShell parse validity matters
PowerShell behavior depends heavily on whether the command can be parsed into a structured representation.

If parse fails:
- explicit deny/ask rules must still work on raw command text
- exact allow can only short-circuit in a narrower, safer subset of cases
- degraded fallback scanning is used to avoid losing deny coverage entirely
- generic ask is used when structural confidence is absent

### Compatibility requirement
A rewrite should preserve:
- parser-valid vs parser-invalid distinction
- parse-failed fallback deny scanning
- fail-safe degradation on parse failure

---

## 4.5 PowerShell collects post-parse decisions then reduces them
Once parse succeeds, PowerShell gathers decisions from multiple checks into one set and reduces with precedence.

Typical decision sources include:
- deferred ask rules
- command safety checks
- `using` statements
- `#Requires` directives
- provider-path checks
- UNC path checks
- subcommand deny/ask checks
- `cd` + `git` guard
- bare-repo/git-internal-path guards
- path constraints
- exact allow
- read-only allow
- mode allow
- file-redirection ask

### Compatibility requirement
A rewrite should strongly prefer an explicit accumulation/reduction model, because it prevents “early ask masks later deny” bugs.

---

## 4.6 PowerShell provider-path and UNC hardening
PowerShell checks command arguments for:
- non-filesystem provider paths, such as registry/env/function/alias/variable/cert/wsman providers
- UNC paths that may trigger network access and credential leakage

These checks operate on parsed arguments and normalized forms, not raw text only.

### Compatibility requirement
A rewrite should preserve:
- provider-path detection
- UNC detection on normalized argument values
- the rule that these require prompting rather than silently counting as read-only

---

## 4.7 PowerShell `using` and `#Requires` directives are prompt-worthy
PowerShell specifically treats these as risky because they can trigger loading of:
- modules
- assemblies
- runtime requirements with side effects

These constructs are not just syntax trivia; they can load code.

### Compatibility requirement
A rewrite should preserve a dedicated prompt path for commands containing:
- `using` statements
- `#Requires` directives

---

## 4.8 PowerShell subcommand extraction
PowerShell extracts subcommands from parsed command structure, including nested commands from control-flow constructs.

This is used so dangerous commands hidden inside larger structures are still checked.

### Compatibility requirement
A rewrite should preserve subcommand extraction that sees through:
- pipelines
- control-flow containers
- nested command positions that still represent executable commands

---

## 4.9 PowerShell `cd`/path-resolution namespace guard
PowerShell has a broader concept than Bash’s `cd` guard.
It treats both cwd-changing cmdlets and path-namespace-changing operations as dangerous in compounds.

This includes:
- `Set-Location`
- `Push-Location`
- `Pop-Location`
- `New-PSDrive` and certain aliases/platform-specific forms

### Rationale
Subsequent relative or drive-prefixed paths may resolve differently at runtime than the validator assumed.

### Compatibility requirement
A rewrite should preserve the concept:
- any compound command that changes path-resolution context may invalidate static path safety for later statements

---

## 4.10 PowerShell `cd` + `git` guard
PowerShell, like Bash, has a dedicated prompt path for compound commands that combine directory/path-context change with git.

### Compatibility requirement
Preserve this behavior explicitly.

---

## 4.11 PowerShell git hardening
PowerShell includes several git-specific protections parallel to Bash.

### 4.11.1 Bare repository indicators in cwd
If cwd looks like an unsafe bare repo, git commands require approval.

### 4.11.2 Writing git-internal paths before git execution
Commands that write:
- `HEAD`
- `objects/...`
- `refs/...`
- `hooks/...`
- `.git/...`

and then run git require approval.

### 4.11.3 Archive extraction before git execution
Archive extraction tools are treated specially because archive contents are opaque.
A compound command that extracts an archive and then runs git requires approval, because archive contents may plant bare-repo indicators/hooks before git runs.

### Compatibility requirement
A rewrite should preserve all three git-hardening behaviors.

---

## 4.12 PowerShell read-only classification
PowerShell read-only logic is based on:
- AST-derived security flags
- command/cmdlet allowlists
- external command allowlists
- per-flag validation
- output-redirection checks
- statement/pipeline structure
- nested-command rejection
- command-name type classification

### Important behaviors
A PowerShell command is not read-only if it contains features such as:
- script blocks
- subexpressions
- expandable strings in sensitive contexts
- splatting
- member invocations
- assignments
- stop-parsing constructs
- unsafe redirections
- cwd-changing compounds
- nested commands

### Compatibility requirement
A rewrite should preserve the rule that read-only classification requires both:
- a known-safe command family
- a structurally safe statement shape

---

## 4.13 PowerShell name-type classification matters
PowerShell classifies command names into categories such as cmdlet/function/application-like forms.

This is critical because a local script/executable path may look like a safe cmdlet after superficial normalization.

### Compatibility requirement
A rewrite should preserve a distinction like:
- cmdlet/function-like command name
- application/script/path-like command name

Application/script/path-like names must not inherit cmdlet allow rules automatically.

---

## 4.14 PowerShell safe-output cmdlets are tightly constrained
Some pipeline-tail/output-formatting cmdlets are treated as harmless only in narrow circumstances.

Important theme:
- name-only classification is not enough
- arguments can leak secrets or execute expression logic
- therefore some output cmdlets are only harmless with zero arguments or with argument-level leak checks

### Compatibility requirement
A rewrite should preserve:
- arg-sensitive treatment of formatting/output cmdlets
- rejection of variable-/expression-/hashtable-/scriptblock-like values in contexts that can leak or evaluate them

---

## 4.15 PowerShell external command validation
PowerShell delegates certain external command families to argument validators similar to Bash’s read-only tables.

Notable families include:
- `git`
- `gh`
- `docker`
- `dotnet`
- various Windows-native utilities

### Important invariant
Even when invoked from PowerShell, these still need:
- argument validation
- dangerous global-flag rejection
- variable-expansion-sensitive rejection
- network/exfiltration-aware handling for some subcommands

### Compatibility requirement
A rewrite should preserve external-command validation as a dedicated subsystem, not assume PowerShell cmdlet rules cover it.

---

## 4.16 PowerShell Windows sandbox policy refusal
PowerShell has a platform-specific policy behavior on native Windows:
- native Windows sandboxing is unavailable
- if enterprise policy requires sandboxing and forbids unsandboxed commands, PowerShell must refuse execution rather than silently run unsandboxed

This is checked in both validation and call-time paths.

### Compatibility requirement
A rewrite should preserve:
- native-Windows policy refusal when sandbox is mandatory but unavailable
- defense in depth by checking both pre-validation and call-time execution paths

---

## 4.17 PowerShell backgrounding behavior
PowerShell supports the same classes of backgrounding as Bash:
- explicit background request
- timeout-driven backgrounding
- assistant-mode blocking-budget backgrounding
- user-initiated backgrounding of a registered foreground task

### Compatibility requirement
Preserve the same task/provenance distinctions as Bash.

---

## 5. Normative safety invariants to preserve

These are the most important shell-specific invariants discovered in this pass.

## 5.1 Deny must dominate ask and allow
If any later shell subcommand or path check yields deny, that deny must win over earlier asks or allows.

Failure mode if omitted:
- explicit deny on a dangerous subcommand can be masked by an earlier prompt-worthy or allow-worthy subcommand

---

## 5.2 Sandbox routing is per invocation
Whether Bash/PowerShell runs sandboxed must be decided for each command invocation, not only by a session-global mode.

Failure mode if omitted:
- excluded commands and explicit overrides cannot be modeled correctly

---

## 5.3 Read-only classification is argument- and structure-sensitive
A command name on a safe list is not sufficient.
Flags, redirections, expression forms, compound structure, and platform semantics all matter.

Failure mode if omitted:
- commands with write/network/code-exec flags become silently auto-allowed

---

## 5.4 Deny/ask normalization is intentionally stronger than allow normalization
The system deliberately strips more wrappers/prefixes/aliases for blocking than for granting.

Failure mode if omitted:
- trivial bypasses like env-var prefixes or alias/module variants evade deny rules

---

## 5.5 UNC/provider/network-triggering path checks must happen before trusting read-only classification
Both shell systems include explicit logic to avoid classifying network-triggering or non-filesystem provider accesses as harmless.

Failure mode if omitted:
- SMB/WebDAV credential-leak paths or registry/env provider reads get auto-allowed incorrectly

---

## 5.6 `cd`/path-context-changing compounds require special treatment
Any compound command that changes path resolution before subsequent operations can invalidate static path reasoning.

Failure mode if omitted:
- relative-path validation is performed against the wrong runtime location

---

## 5.7 Git/hook/bare-repo hardening is mandatory
The shell implementation clearly contains production-hardened mitigations for git hook and bare-repository attacks.

Failure mode if omitted:
- commands can plant hooks/repo indicators and trigger git execution in the same or a later step

---

## 5.8 Parse failure must degrade fail-safe
When parsing fails, explicit deny/ask logic must still work, but structural auto-allow must narrow or disappear.

Failure mode if omitted:
- degraded parser paths become bypass paths

---

## 5.9 Safe-output pipeline tails must still validate arguments
Formatting/output commands are only harmless when their arguments are harmless.

Failure mode if omitted:
- secret-bearing or executable expressions piggyback through “safe output” cmdlets

---

## 5.10 Native-Windows PowerShell must honor mandatory-sandbox policy by refusing execution
Failure mode if omitted:
- enterprise policy is silently bypassed on Windows

---

## 6. Decision matrices

## 6.1 Bash sandbox routing matrix

Inputs:
- sandbox globally enabled and available?
- command present?
- `dangerouslyDisableSandbox` set?
- policy allows unsandboxed commands?
- command matches excluded-command routing?

Decision:

| Condition | Use sandbox? |
|---|---:|
| sandbox unavailable/disabled | no |
| no command string | no |
| override set AND unsandboxed allowed | no |
| excluded-command match | no |
| otherwise | yes |

---

## 6.2 Bash approval precedence

At minimum, preserve this effective precedence:

1. explicit deny rules
2. explicit ask rules
3. syntax/structural safety asks
4. dangerous path / redirection denies or asks
5. git/cd special-case asks
6. sandbox auto-allow or mode allow
7. read-only allow
8. passthrough/prompt

Exact internal ordering can vary, but not in ways that violate the invariants above.

---

## 6.3 PowerShell approval precedence

Preserve:

1. pre-parse deny rules
2. post-parse reduce: deny > ask > allow > passthrough
3. if unresolved, per-subcommand approval accumulation and prompt suggestions

This is the safest shape for maintaining compatibility.

---

## 7. Rewrite checklist

A shell rewrite should explicitly include all of the following:

- per-command sandbox routing
- policy-controlled `dangerouslyDisableSandbox`
- excluded-command routing for Bash
- AST-first parsing with fail-safe fallback
- exact/prefix/wildcard rule matching
- asymmetric normalization for deny vs allow
- subcommand-aware compound-command checking
- dedicated syntax/injection safety layer
- explicit validation of redirected output targets
- read-only classification with flag validation
- git/bare-repo/internal-path hardening
- cd/path-context-change special handling
- provider-path and UNC hardening
- PowerShell collect-then-reduce precedence model
- PowerShell name-type distinction between cmdlets and application/script/path-like commands
- arg-sensitive treatment of safe-output/formatting cmdlets
- native-Windows mandatory-sandbox refusal for PowerShell
- backgrounding semantics with stable task identity and provenance labels

If any of those are missing, the rewrite is at significant risk of safety or compatibility regressions.

---

## 8. Confidence and limits

High confidence:
- the core safety structure above is directly supported by inspected code and comments
- many behaviors are clearly intentional hardening, not incidental implementation details

Lower confidence:
- I did not exhaustively enumerate every individual safe flag for every Bash read-only command family in this document
- I did not inspect every UI permission-dialog component for shell tools in this pass

That said, this document captures the safety model and compatibility-critical shell behaviors that a clean-room rewrite should preserve.