# Path and filesystem safety for a clean-room rewrite

This document captures the path-handling, filesystem-hardening, and platform-specific safety behavior that a compatible rewrite should preserve.

It focuses on security and correctness behavior around:
- path normalization and comparison
- symlink-aware permission checks
- UNC / SMB / WebDAV hardening
- protected config/settings/skill paths
- internal harness-managed path carve-outs
- special-file and device-file protections
- read-before-write / stale-read filesystem invariants
- platform quirks that affect path safety

Companion docs:
- `docs/permission-engine.md`
- `docs/bash-and-powershell-safety.md`
- `docs/tool-contracts.md`
- `docs/implementation-notes-and-gotchas.md`

Primary inspected sources for this pass:
- `src/utils/permissions/filesystem.ts`
- `src/utils/fsOperations.ts`
- `src/tools/FileReadTool/FileReadTool.ts`
- `src/tools/FileEditTool/FileEditTool.ts`
- `src/tools/FileWriteTool/FileWriteTool.ts`
- `src/tools/NotebookEditTool/NotebookEditTool.ts`
- `src/tools/BashTool/pathValidation.ts`
- `src/tools/PowerShellTool/pathValidation.ts`

---

## 1. Scope

This document is about filesystem safety behavior, not just permission-rule matching.

The system does **not** treat path handling as a thin utility layer. Path resolution, comparison, normalization, and special-case blocking are part of the security model.

A rewrite should preserve that model.

---

## 2. Core design principle

Filesystem authorization is evaluated against more than the literal user-supplied string.

At minimum, the implementation reasons about:
- the lexical/original path
- normalized path forms
- resolved symlink/canonical forms where safe to compute
- working-directory containment after normalization
- protected internal/config-sensitive subtrees
- dangerous platform-specific path syntaxes

### Rewrite requirement
Preserve filesystem safety as a **multi-stage path safety pipeline**, not as a single string-prefix check.

---

## 3. Canonical path-safety pipeline

A compatible rewrite should conceptually apply checks in this shape:

```ts
function evaluateFilesystemAccess(path, operation, context): Decision {
  const expanded = expandPath(path)
  const pathsToCheck = getPathsForPermissionCheck(expanded) // original + resolved forms when safe

  rejectEarlyIfUncOrSuspiciousPlatformSyntax(pathsToCheck)
  applyExplicitDenyRules(pathsToCheck, operation)
  applyInternalHarnessCarveoutsIfApplicable(expanded, operation)
  applyProtectedPathSafetyChecks(pathsToCheck, operation)
  applyAskRules(pathsToCheck, operation)
  allowIfWorkingDirectoryModePermits(pathsToCheck, operation)
  allowIfMatchingExplicitAllowRule(pathsToCheck, operation)
  otherwiseAsk()
}
```

Exact layering may differ by tool and operation type, but the rewrite should preserve the semantic ordering described below.

---

## 4. Path expansion and comparison invariants

## 4.1 Input paths are expanded before downstream matching
Tools normalize/expand incoming file paths before permission matching and other checks.

This is used to prevent bypasses involving:
- `~`
- relative paths
- mixed separator spellings
- redundant `./` structure in some checks

### Rewrite requirement
Preserve early path expansion/normalization before hook matching, permission checks, and protected-path checks.

---

## 4.2 Path comparisons are case-normalized for safety-sensitive checks
The implementation lowercases paths for comparison in several security-sensitive places, even though not all filesystems are case-insensitive.

This is a deliberate safety bias to prevent bypasses such as:
- `.pInsEr/settings.json`
- `.GIT/config`
- mixed-case dangerous filenames or directories

### Rewrite requirement
Preserve case-insensitive comparison for security checks involving protected directories/files and related containment checks.

---

## 4.3 Containment checks are relative-path based, not naive prefix checks
Directory containment uses normalized relative-path logic rather than bare `startsWith` on raw input.

This prevents false positives and traversal bypasses such as:
- `/allowed-other` incorrectly matching `/allowed`
- `../` escape segments
- separator and root mismatches

### Rewrite requirement
Preserve path containment via normalized relative-path semantics, not raw string prefix matching.

---

## 4.4 macOS symlink-root aliases are normalized during containment checks
The implementation specifically normalizes common macOS alias roots such as:
- `/private/var` ↔ `/var`
- `/private/tmp` ↔ `/tmp`

This avoids false denials when one side of a comparison is canonical and the other is not.

### Rewrite requirement
Preserve macOS alias-root normalization for containment comparisons.

---

## 5. Symlink-aware permission checking

## 5.1 Permission checks reason about both original and resolved paths
The permission layer frequently evaluates both:
- the original path string
- resolved symlink/canonical forms

This prevents bypasses where a harmless-looking path points at a protected or out-of-scope target via symlink traversal.

### Rewrite requirement
Preserve dual checking of original and resolved path forms for permission and safety decisions.

---

## 5.2 Resolved working directories are compared symmetrically with resolved candidate paths
Working directories are also expanded into resolved forms before comparison.

Without this, resolved candidate paths could fail containment against unresolved working roots, especially on macOS symlinked system roots.

### Rewrite requirement
Preserve symmetric resolution of both candidate paths and allowed working directories.

---

## 5.3 Resolution must degrade safely when canonicalization is unsafe or unavailable
The implementation does not assume every path can be safely `realpath`'d.

If path resolution fails because of:
- ENOENT
- broken symlink
- permission error
- loop
- unsupported/special-file behavior

it falls back to the original path rather than crashing.

### Rewrite requirement
Preserve safe fallback when path canonicalization cannot be completed.

---

## 6. UNC / SMB / WebDAV hardening

This is one of the most important security behaviors to preserve.

## 6.1 UNC/network-looking paths are blocked before filesystem probing
The system intentionally avoids filesystem probing on paths that look like UNC/network paths, including forms starting with:
- `\\`
- `//`

Why:
- probing UNC paths on Windows can trigger SMB/WebDAV authentication
- that can leak credentials (for example NTLM) to attacker-controlled endpoints

### Rewrite requirement
Preserve **no filesystem probing before permission decision** for UNC/network-looking paths.

---

## 6.2 UNC/network hardening exists in multiple layers as defense in depth
This behavior appears in several places, not just one:
- safe path resolution skips UNC probing
- read/edit/write/notebook validation skip filesystem I/O for UNC paths
- read permissions have explicit early UNC handling
- dangerous-file safety checks also treat UNC/network spellings as unsafe
- suspicious-path detection also includes UNC detection

### Rewrite requirement
Preserve multi-layer UNC hardening, not a single centralized check only.

---

## 6.3 UNC/network paths should generally force ask/manual approval rather than silent allow
The implementation does not treat UNC/network paths as ordinary local files merely because a path rule matches textually.

### Rewrite requirement
Preserve conservative manual-gate behavior for UNC/network filesystem access.

---

## 7. Special-file and device-file safety

## 7.1 Path canonicalization avoids `realpath` on dangerous special files
Before resolving a path, the implementation checks whether the path refers to special file kinds such as:
- FIFO
- socket
- character device
- block device

Reason:
- some resolution/probing operations can block or behave unexpectedly on such files

### Rewrite requirement
Preserve special-file prechecks before canonicalization/probing.

---

## 7.2 FileRead blocks specific device paths known to hang or never terminate
The read tool hard-blocks device-like paths such as:
- `/dev/zero`
- `/dev/random`
- `/dev/urandom`
- `/dev/full`
- `/dev/stdin`
- `/dev/tty`
- `/dev/console`
- `/dev/stdout`
- `/dev/stderr`
- `/dev/fd/0..2`
- Linux `/proc/.../fd/0..2` aliases

Reason:
- some block waiting for input
- some produce effectively infinite output
- some are nonsensical for file reading

### Rewrite requirement
Preserve explicit blocked-device-path handling for read operations.

---

## 7.3 Safe special files are not necessarily blanket-banned
The implementation does not treat every special path as forbidden. It bans known-bad read targets and otherwise uses narrower safeguards.

### Rewrite requirement
Preserve targeted rather than indiscriminate special-file blocking, unless the rewrite intentionally adopts a stricter documented policy.

---

## 8. Suspicious Windows path syntax hardening

The implementation treats several Windows path forms as suspicious enough to require manual approval.

## 8.1 Alternate data stream syntax is suspicious
Examples include forms like:
- `file.txt:stream`
- `file.txt::$DATA`

These are treated as suspicious on Windows/WSL because colon syntax can address NTFS alternate data streams.

### Rewrite requirement
Preserve ADS-style path detection and conservative handling.

---

## 8.2 8.3 short names are suspicious
Examples include:
- `GIT~1`
- `PINSER~1`
- `SETTIN~1.JSON`

Reason:
- they can bypass string-based protected-path matching

### Rewrite requirement
Preserve short-name detection and conservative handling.

---

## 8.3 Long path prefixes are suspicious
Examples include:
- `\\?\C:\...`
- `\\.\C:\...`
- `//?/C:/...`
- `//./C:/...`

### Rewrite requirement
Preserve long-path-prefix detection and conservative handling.

---

## 8.4 Trailing dots/spaces and DOS device-name suffixes are suspicious
Examples include:
- `.git.`
- `.pinser `
- `settings.json.PRN`
- `.bashrc.AUX`

Reason:
- Windows path canonicalization can collapse or reinterpret them in ways that bypass string checks

### Rewrite requirement
Preserve trailing-dot/space and DOS-device-name suspicious-path detection.

---

## 8.5 Three-or-more-dot path components are suspicious
Examples include components such as `.../`.

Reason:
- these can be used to create confusing or bypass-oriented path forms

### Rewrite requirement
Preserve suspicious handling for multi-dot path components.

---

## 8.6 These Windows-pattern checks are intentionally applied broadly
The implementation comments explicitly justify checking these patterns even outside native Windows, because Windows-like filesystems or mount behaviors can appear elsewhere.

### Rewrite requirement
Preserve broad suspicious-path detection unless there is a carefully reasoned compatibility change.

---

## 9. Protected config-sensitive paths

## 9.1 Some files and directories are built-in dangerous paths
The implementation has built-in protected-path concepts for files such as:
- `.gitconfig`
- `.gitmodules`
- shell rc/profile files
- `.mcp.json`
- `.pinser.json`

and directories such as:
- `.git`
- `.vscode`
- `.idea`
- `.pinser`

These are not just user policy; they are built-in hardening.

### Rewrite requirement
Preserve built-in dangerous-path protection for configuration/executable/sensitive directories and files.

---

## 9.2 Protected-path matching is case-insensitive for safety
This prevents mixed-case bypasses for paths like:
- `.Git/config`
- `.PiNsEr/settings.local.json`

### Rewrite requirement
Preserve case-insensitive protected-path checks.

---

## 9.3 `.pinser/worktrees/` is a deliberate exception inside an otherwise dangerous directory
The implementation treats `.pinser` as dangerous generally, but does not blanket-block the structural worktree subtree used by the system.

### Rewrite requirement
Preserve the `.pinser/worktrees/` carve-out if the rewrite retains equivalent worktree storage under protected config space.

---

## 9.4 Pinser settings files are specially protected
Project and related settings files such as `.pinser/settings.json` and `.pinser/settings.local.json` receive special handling and cannot be treated as ordinary files.

The implementation also normalizes path structure first to avoid bypasses involving redundant path segments.

### Rewrite requirement
Preserve dedicated settings-file protection with normalized-path comparison.

---

## 9.5 Pinser-owned command/agent/skill directories are specially protected
Paths under project-local Pinser-managed subtrees such as:
- `.pinser/commands/`
- `.pinser/agents/`
- `.pinser/skills/`

are treated as internal/config-sensitive.

### Rewrite requirement
Preserve built-in protection for Pinser-owned command/agent/skill directories.

---

## 10. Internal harness-managed carve-outs

Not all internal paths are blocked. Some are intentionally always-readable or always-writable because the harness itself owns them.

## 10.1 Some internal writable paths bypass normal dangerous-directory blocking
Examples include:
- current-session plan files
- current-session scratchpad files
- current job directory files (under validated jobs root)
- agent memory files
- default memdir/auto-memory files in the built-in location
- project `.pinser/launch.json` preview config

These are allowed even when they sit under otherwise dangerous roots.

### Rewrite requirement
Preserve internal writable-path carve-outs for harness-owned state.

---

## 10.2 Job-directory write carve-out is guarded against env hijack and symlink escape
The implementation does not blindly trust a job-dir environment variable.

It verifies:
- the job dir itself resolves under the expected jobs root
- all target path forms resolve within that validated job dir

### Rewrite requirement
Preserve validation of any env-provided internal writable root before granting implicit access.

---

## 10.3 Internal readable paths include harness persistence and tool state
Examples include:
- session memory
- project/session storage under the project dir
- current-session plan files
- tool-results storage
- scratchpad
- project temp directory
- agent memory
- auto-memory path
- task/team coordination directories
- bundled skill extraction root

### Rewrite requirement
Preserve explicit internal-readable carve-outs for harness-owned persistence domains.

---

## 10.4 Bundled-skill extraction safety depends on an unpredictable subtree
The bundled skill extraction root is protected not merely by location but by a per-process random nonce in the path.

This defends against temp-directory squatting/precreation attacks.

### Rewrite requirement
Preserve unpredictable per-process or per-session extraction roots for bundled/generated skill content.

---

## 11. `.pinser/**` editing exception model

## 11.1 `.pinser/**` is blocked by safety checks by default
Even if it is under the working directory, `.pinser/**` editing is not treated like ordinary project editing.

### Rewrite requirement
Preserve `.pinser/**` as safety-sensitive by default.

---

## 11.2 Session-scoped `.pinser/**` allow rules can bypass default safety blocking
The implementation allows certain session-scoped `.pinser/**` rules to bypass the built-in safety block.

Important constraints:
- this is limited to session-scoped rules
- the rule must really scope under `.pinser/`
- traversal-like patterns are rejected
- narrowed skill-only scopes are supported

### Rewrite requirement
Preserve the distinction between built-in `.pinser/**` blocking and explicitly granted session-scoped exceptions.

---

## 11.3 Skill-specific session exceptions are intentionally narrower than broad `.pinser/**` access
When editing a path under `.pinser/skills/{name}/`, the implementation can suggest permission for just that skill subtree rather than all of `.pinser/`.

### Rewrite requirement
Preserve narrowed skill-subtree exception suggestions rather than forcing all-or-nothing `.pinser` grants.

---

## 12. Read-before-write invariant

This is one of the most important correctness invariants.

## 12.1 File mutation generally requires a prior read
For ordinary file edit/write operations, the tool expects the file to have been read earlier in the session before mutation is allowed.

### Rewrite requirement
Preserve read-before-write as the default invariant for file mutation.

---

## 12.2 Partial reads do not satisfy the invariant
For edit/write flows, a partial read is not sufficient.

The implementation explicitly tracks whether the remembered read view was partial and rejects mutation if so.

### Rewrite requirement
Preserve the distinction between full reads and partial reads for mutation eligibility.

---

## 12.3 Notebook edits also enforce read-before-write
Notebook editing is not exempt. The notebook must have been read first, or the edit is rejected.

### Rewrite requirement
Preserve notebook read-before-write behavior.

---

## 12.4 `.ipynb` file edits are routed to the notebook-specific tool path
The ordinary file edit tool rejects notebook files and instructs callers to use the notebook edit tool instead.

### Rewrite requirement
Preserve notebook-specific edit routing rather than allowing generic text editing of notebook JSON through the normal file-edit path.

---

## 13. Stale-read protection

## 13.1 Mutation checks compare current file state against the remembered read snapshot time
Before mutation, the system checks whether the file appears to have changed since it was read.

### Rewrite requirement
Preserve stale-read detection before mutation.

---

## 13.2 Windows timestamp false positives are mitigated by content fallback in some mutation flows
For edit/write execution paths, timestamp-only change detection is not always trusted.

If mtime indicates change but a prior read was a full read and content is identical, the implementation can proceed.

Reason:
- Windows/cloud-sync/AV/other tooling can perturb timestamps without semantic content change

### Rewrite requirement
Preserve content-based fallback for suspicious timestamp-only modifications, at least where full prior content is available.

---

## 13.3 Atomicity-sensitive sections avoid async gaps between freshness check and write
Comments in the mutation tools emphasize not inserting asynchronous work between:
- the final freshness/state check
- the actual disk write

Reason:
- doing so introduces race windows where concurrent writes can interleave

### Rewrite requirement
Preserve a tight, effectively atomic read-check-write critical section.

---

## 14. Tool-specific filesystem safety behavior

## 14.1 FileRead validate step avoids dangerous I/O before permission approval
Before permission is granted, the read tool restricts itself to safe checks such as:
- string-based path checks
- deny-rule matching
- binary-extension heuristics
- blocked-device-path checks

It avoids unsafe filesystem probing for UNC/network paths.

### Rewrite requirement
Preserve validate-time avoidance of risky I/O on unapproved paths.

---

## 14.2 FileEdit and FileWrite also avoid filesystem probing for UNC paths in validation
These tools intentionally skip `stat`/existence/read operations on UNC-like paths until permission handling has a chance to block or gate them.

### Rewrite requirement
Preserve UNC-safe validate behavior for edit/write tools.

---

## 14.3 NotebookEdit follows the same UNC-safe pattern
Notebook editing also avoids filesystem probing for UNC paths before permission gating.

### Rewrite requirement
Preserve UNC-safe validation across notebook mutation paths too.

---

## 14.4 Bash/PowerShell path validation participates in the same filesystem safety model
Shell tool path validation is not independent of filesystem safety. It reuses permission/path-validation helpers and protected-path logic.

Examples include:
- dangerous removal path handling
- allowed-working-directory enforcement
- internal path safety checks
- rule-based suggestions

### Rewrite requirement
Preserve shared filesystem-safety semantics across shell and non-shell tools.

---

## 15. Compound shell/path safety behaviors worth preserving

## 15.1 Shell path validation strips safe wrapper commands before inspecting the real command
This avoids bypasses such as wrapping dangerous commands in utility wrappers like `timeout` or `nice`.

### Rewrite requirement
Preserve wrapper stripping before shell path classification.

---

## 15.2 Shell path parsing respects `--` end-of-options behavior
This prevents attackers from hiding dangerous path arguments merely by giving them flag-like spellings after `--`.

### Rewrite requirement
Preserve `--` semantics in shell path extraction.

---

## 15.3 Compound shell commands with `cd` plus output redirection are forced to manual approval
Reason:
- redirection targets may be evaluated relative to the wrong working directory if `cd` occurs earlier in the command

### Rewrite requirement
Preserve manual gating for compound `cd` + redirection cases.

---

## 15.4 Process substitution in shell commands is forced to manual approval
Reason:
- hidden writes can occur through process substitution without obvious redirect targets

### Rewrite requirement
Preserve manual gating for process substitution forms.

---

## 16. Platform-specific path quirks

## 16.1 macOS screenshot filenames may differ only by a thin-space vs normal-space before AM/PM
The read tool includes a specific fallback for screenshot filenames where the separator before `AM`/`PM` may be:
- regular space
- narrow no-break/thin space (U+202F)

### Rewrite requirement
Preserve the macOS screenshot filename alternate-space fallback if the rewrite aims for behavioral compatibility.

---

## 16.2 Temp-directory symlink resolution matters on macOS
The temp root may resolve differently (`/tmp` vs `/private/tmp`), so temp and scratchpad containment checks need canonicalization-aware handling.

### Rewrite requirement
Preserve canonical temp-root handling so internal temp/scratchpad paths compare correctly.

---

## 16.3 Windows and WSL path semantics are security-relevant, not just portability details
The implementation treats Windows/WSL path oddities as security-sensitive inputs.

### Rewrite requirement
Preserve explicit Windows/WSL path hardening rather than relegating it to generic portability helpers.

---

## 17. Suggested clean-room interfaces

A rewrite should expose interfaces roughly like:

```ts
type PathSafetyCheck =
  | { safe: true }
  | { safe: false; message: string; classifierApprovable: boolean }

type PathsForPermissionCheck = readonly string[]

interface FilesystemSafety {
  getPathsForPermissionCheck(path: string): PathsForPermissionCheck
  pathInWorkingPath(path: string, workingPath: string): boolean
  pathInAllowedWorkingPath(path: string, context: ToolPermissionContext): boolean
  checkPathSafetyForAutoEdit(path: string): PathSafetyCheck
  checkEditableInternalPath(path: string, input: object): PermissionResult
  checkReadableInternalPath(path: string, input: object): PermissionResult
}
```

The exact type names can differ, but the semantics above should remain close.

---

## 18. Critical invariants for a rewrite

## 18.1 Never filesystem-probe UNC/network paths before permission gating
Failure mode:
- credential leakage via SMB/WebDAV/UNC probing

## 18.2 Evaluate both lexical and resolved path forms where safe
Failure mode:
- symlink bypasses around protected paths or working-directory boundaries

## 18.3 Protected config-sensitive paths must remain built-in hardening, not user-policy only
Failure mode:
- accidental self-modification of settings/skills/config state

## 18.4 Read-before-write must require a full, fresh read
Failure mode:
- stale or partial-view edits that silently corrupt files

## 18.5 Mutation freshness checks must account for Windows timestamp false positives
Failure mode:
- bogus “file changed” errors in normal Windows/cloud-sync environments

## 18.6 Notebook edits must stay on a dedicated notebook path
Failure mode:
- invalid notebook mutation through generic text-edit flows

## 18.7 Internal harness-owned directories need explicit carve-outs with validation
Failure mode:
- harness state becomes unusable, or env-controlled roots become privilege-escalation paths

## 18.8 Shell path validation must preserve wrapper stripping, `--` semantics, and compound-command manual gates
Failure mode:
- path safety bypass through shell syntax edge cases

## 18.9 Special-file and blocked-device protections must remain in place
Failure mode:
- hangs, infinite-output reads, or unsafe probing behavior

---

## 19. Confidence and limits

High confidence:
- UNC hardening, dangerous-path handling, protected `.pinser`/settings behavior, internal path carve-outs, read-before-write invariants, stale-read protection, blocked-device reads, notebook-specific editing, and the macOS screenshot workaround are directly grounded in inspected code

Lower confidence:
- this document abstracts some shared helper behavior used indirectly by shell path validation and permission suggestion generation, and does not restate every individual path-pattern or command parser rule already documented elsewhere

That is deliberate: this file is intended to be the filesystem/path hardening spec, not a duplicate of the shell-safety or permission-engine docs.
