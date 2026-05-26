# Agent resume and sidechains for a clean-room rewrite

This document describes the persistence, resume, and reconstruction semantics for subagents / background agents / sidechains. It focuses on the contracts a compatible rewrite should preserve around agent transcripts, forked context, sidecar metadata, worktree restoration, and replacement-state recovery.

This is a distinct compatibility surface from main-session transcript persistence. A rewrite can preserve the main conversation perfectly and still break agent resumption, forked agents, worktree-isolated agents, or long-running background task recovery.

Companion docs:
- `docs/task-and-swarm.md`
- `docs/transcript-and-persistence-semantics.md`
- `docs/message-normalization-for-api.md`
- `docs/tool-contracts.md`
- `docs/implementation-notes-and-gotchas.md`

Primary inspected sources for this pass:
- `src/tools/AgentTool/runAgent.ts`
- `src/tools/AgentTool/resumeAgent.ts`
- `src/utils/sessionStorage.ts`
- `src/utils/toolResultStorage.ts`
- `src/utils/crossProjectResume.ts`

---

## 1. Purpose

Agent execution is not ephemeral.

The runtime preserves enough state to support:
- async/background subagent continuation
- resumed fork agents with inherited parent context
- resumed worktree-isolated agents
- agent transcript browsing after task eviction
- sidechain-aware transcript loading
- prompt-cache-safe reapplication of content-replacement decisions
- restoration of agent type and display description

A clean-room rewrite should treat this as a first-class subsystem:

```ts
type AgentPersistenceAndResume = {
  recordSidechainTranscript(...): Promise<void>
  writeAgentMetadata(...): Promise<void>
  readAgentMetadata(...): Promise<AgentMetadata | null>
  getAgentTranscript(agentId): Promise<AgentTranscript | null>
  resumeAgentBackground(...): Promise<ResumeAgentResult>
}
```

---

## 2. Conceptual model

## 2.1 Agents write sidechains, not main-thread continuations
Subagent messages are persisted as sidechain transcript entries associated with an `agentId` and marked as sidechain content.

They are not simply appended as normal continuation of the foreground conversation chain.

### Rewrite requirement
Preserve subagent execution as a separate transcript branch/domain with explicit `agentId` identity.

---

## 2.2 Agent resume is transcript replay plus contextual reconstruction
Resuming an agent is not merely “continue from last prompt”.
It reconstructs:
- the agent’s message chain
- the agent type
- the correct cwd/worktree if still valid
- content-replacement state
- fork-specific system prompt behavior
- async task registration and lifecycle wiring

### Rewrite requirement
Preserve agent resume as a multi-part state reconstruction flow.

---

## 2.3 Agent identity is stable across resume
The resumed agent reuses the original `agentId` rather than inventing a new logical agent identity.

### Rewrite requirement
Preserve stable agent identity across resume.

This matters for:
- transcript lookup
- output files
- UI/task continuity
- metadata sidecars

---

## 3. Sidechain transcript persistence

## 3.1 Agent transcripts are stored separately from the main transcript file
Each subagent writes to a separate JSONL transcript under a session-scoped `subagents/` area.

Conceptually:

```text
<project>/<sessionId>/subagents/agent-<agentId>.jsonl
```

Optional grouping subdirectories may appear between `subagents/` and the transcript file.

### Rewrite requirement
Preserve separate per-agent transcript files under the session scope.

---

## 3.2 Sidechains may be grouped into subdirectories
The system supports an optional subdirectory under `subagents/` to group related agent transcripts, e.g. workflow runs.

Conceptually:

```text
<project>/<sessionId>/subagents/<subdir>/agent-<agentId>.jsonl
```

This subdirectory is chosen before the agent starts and affects transcript path resolution.

### Rewrite requirement
Preserve optional transcript subdirectory grouping for agents.

---

## 3.3 Initial agent context is persisted before the query loop starts
An agent records its initial messages before streaming/turn execution begins.
This initial transcript includes:
- inherited fork context, if any
- the prompt messages provided to the agent

### Rewrite requirement
Preserve eager recording of initial sidechain transcript state before agent execution proceeds.

---

## 3.4 Later sidechain messages are recorded incrementally with parent continuity
After startup, each recordable agent message is written incrementally and linked to the prior recorded message UUID.

### Rewrite requirement
Preserve incremental sidechain append with explicit chain continuity.

---

## 3.5 Only sidechain-marked messages for the specific agent belong to its resumed transcript
When reading an agent transcript back, the loader filters transcript entries to those that:
- belong to the target `agentId`
- are marked as sidechain entries

### Rewrite requirement
Preserve strict per-agent filtering when reconstructing an agent transcript.

---

## 3.6 Agent transcript reconstruction is leaf-and-chain based
The loader:
- finds candidate messages for the target agent
- identifies the most recent leaf for that agent
- reconstructs the conversation chain backward from that leaf
- then filters to only messages belonging to that agent

This means resume is not simple file-order replay.

### Rewrite requirement
Preserve leaf-based chain reconstruction for sidechains.

---

## 4. Agent metadata sidecars

## 4.1 Agent metadata is stored separately from the transcript JSONL
Each agent also has a sidecar metadata file adjacent to the transcript file.

Conceptually:

```text
<project>/<sessionId>/subagents/.../agent-<agentId>.meta.json
```

### Rewrite requirement
Preserve metadata sidecars separate from transcript body.

---

## 4.2 Agent metadata minimally includes agent type
The metadata records at least:

```ts
type AgentMetadata = {
  agentType: string
  worktreePath?: string
  description?: string
}
```

### Why `agentType` matters
Without it, resuming an agent without explicitly restating the subagent type can silently route to the wrong default agent implementation.

### Rewrite requirement
Preserve durable storage of `agentType` in agent metadata.

---

## 4.3 Worktree path is persisted when the agent was launched in worktree isolation
If an agent was spawned in an isolated worktree, that worktree path is stored in metadata.

### Rewrite requirement
Preserve worktree-path metadata for worktree-isolated agents.

---

## 4.4 Agent description is persisted for UI continuity
The original task description may also be persisted in metadata so a resumed agent can show the original description rather than a placeholder.

### Rewrite requirement
Preserve description sidecar persistence for resumed-agent display continuity.

---

## 4.5 Metadata writes are best-effort and must not block agent startup
The original implementation treats metadata persistence as fire-and-forget / best-effort rather than making it a hard prerequisite for agent execution.

### Rewrite requirement
Preserve non-fatal metadata persistence behavior.

---

## 5. Agent type recovery semantics

## 5.1 Resume routes by persisted agent type when available
On resume, the agent type is restored from metadata.

Behavioral cases:
- if metadata says the agent is a fork agent, resume as fork agent
- else if metadata names a known active agent definition, use that
- else fall back to a general-purpose/default agent

### Rewrite requirement
Preserve persisted-agent-type-first routing on resume.

---

## 5.2 Missing or stale agent types degrade gracefully
If metadata is missing or references an unavailable agent definition, the system falls back rather than crashing.

### Rewrite requirement
Preserve graceful fallback for unknown or missing agent types.

---

## 6. Resume transcript cleanup semantics

## 6.1 Agent resume reuses the same transcript cleanup filters as main-session recovery
Before replaying the agent transcript into a resumed run, the system filters:
- unresolved tool uses
- orphaned thinking-only assistant messages
- whitespace-only assistant messages

### Rewrite requirement
Preserve pre-resume cleanup of sidechain transcripts using the same correctness filters as the main conversation.

---

## 6.2 Resume does not blindly trust stored sidechain transcripts
The stored sidechain transcript is treated as potentially malformed due to interruption, streaming fragmentation, or older bugs.

### Rewrite requirement
Preserve defensive cleanup during agent resume, not just raw transcript replay.

---

## 7. Content-replacement recovery for resumed agents

## 7.1 Agent transcripts have their own persisted content-replacement records
Large-tool-output replacement decisions associated with an agent sidechain are persisted separately and loaded with that agent transcript.

### Rewrite requirement
Preserve per-agent content-replacement records alongside sidechain transcripts.

---

## 7.2 Resumed agent replacement state is reconstructed, not restarted from empty
When resuming an agent, the content-replacement state is rebuilt from:
- the resumed sidechain messages
- the sidechain’s persisted replacement records
- possibly inherited parent replacement mappings

### Rewrite requirement
Preserve replacement-state reconstruction for resumed agents.

---

## 7.3 Parent replacement mappings fill gaps for fork resumes
Fork agents can inherit parent-side replacement decisions that were not newly created inside the sidechain and therefore may not exist as sidechain records.

On resume, the parent’s live replacement map is used to fill these gaps for IDs that appear in the resumed sidechain transcript.

### Rewrite requirement
Preserve inherited replacement-map gap-filling for resumed fork agents.

This is critical for prompt-cache stability.

---

## 7.4 If replacement state is disabled in the parent, subagent reconstruction is also disabled
The resume helper returns no replacement state when the parent feature/state is absent.

### Rewrite requirement
Preserve feature/state-gated replacement reconstruction rather than manufacturing replacement state when the parent did not have it.

---

## 8. Worktree-aware resume semantics

## 8.1 Resumed agent prefers its original worktree cwd when still valid
If metadata includes a worktree path and that directory still exists, resume runs the agent in that worktree directory.

### Rewrite requirement
Preserve worktree-path restoration on resume when the path remains valid.

---

## 8.2 Missing worktrees degrade to parent cwd instead of hard failure
If the recorded worktree path no longer exists or is no longer a directory, resume falls back to the parent/current cwd instead of crashing.

### Rewrite requirement
Preserve graceful cwd fallback when the original worktree has disappeared.

---

## 8.3 Resuming a live worktree bumps its mtime
When the stored worktree directory is still present and is chosen for resume, its modification time is updated so stale-worktree cleanup does not race and delete a just-resumed worktree.

### Rewrite requirement
Preserve the “touch on resume” behavior or an equivalent anti-stale-cleanup safeguard.

This is a subtle but important operational invariant.

---

## 8.4 Resumed non-fork agents recompute their system prompt under the restored cwd
For non-fork agents, resume does not blindly reuse a serialized system prompt; it recomputes the effective prompt under the resumed cwd/worktree context.

### Rewrite requirement
Preserve cwd-sensitive system-prompt recomputation for resumed non-fork agents.

---

## 9. Fork-agent-specific resume semantics

## 9.1 Fork agents are special because they inherit parent context
A fork agent’s original run includes a parent-context slice inherited from the main thread.

### Rewrite requirement
Preserve an explicit fork-context concept distinct from ordinary agent prompts.

---

## 9.2 On original fork spawn, inherited parent context is persisted into the sidechain transcript
The fork’s initial recorded sidechain transcript contains the inherited context from the parent plus the fork prompt messages.

### Rewrite requirement
Preserve persistence of inherited fork context in the sidechain transcript itself.

---

## 9.3 On resume, fork agents must not be given the parent context again
Because the original sidechain transcript already contains the inherited parent slice, resupplying `forkContextMessages` on resume would duplicate that context and can produce duplicate tool-use IDs.

### Rewrite requirement
Preserve the rule:
- original fork run: include inherited fork context
- resumed fork run: do **not** inject the parent context again

This is a major invariant.

---

## 9.4 Fork resumes reuse the parent system prompt, not a recomputed generic agent prompt
Resumed fork agents require the parent’s system prompt (or an equivalent reconstructed parent prompt) so the fork preserves the same cache-identical prefix and inherited behavior.

Behavioral order:
- if the parent rendered system prompt is already available in the tool-use context, reuse it
- otherwise reconstruct an equivalent effective parent system prompt
- if this cannot be done, resume fails rather than silently using the wrong prompt family

### Rewrite requirement
Preserve parent-system-prompt reuse/reconstruction for fork resumes.

---

## 9.5 Fork resumes may run with exact tools rather than a recomputed filtered pool
Resumed fork agents preserve the intended tool set closely rather than always recomputing the generic agent tool pool.

### Rewrite requirement
Preserve the ability for fork resumes to use an exact/restored tool set.

---

## 10. Permission and tool-pool semantics on resume

## 10.1 Resume preserves agent-specific permission mode behavior
An agent definition can impose its own permission mode. On resume, the worker permission context is rebuilt with the selected agent’s permission mode semantics.

### Rewrite requirement
Preserve agent-definition-driven permission context reconstruction on resume.

---

## 10.2 Non-fork resumed agents may assemble a fresh tool pool from current permission/MCP state
For ordinary agents, the tool pool can be rebuilt from:
- current permission context
- current MCP tool state
- current agent definition

### Rewrite requirement
Preserve dynamic tool-pool reconstruction for non-fork resumes.

---

## 11. Async/background task restoration semantics

## 11.1 Resumed agents are re-registered as async/background tasks
Resuming a background agent is not just rebuilding a transcript; it also re-registers an async task entry in the app/task system.

### Rewrite requirement
Preserve task registration as part of agent resume.

---

## 11.2 UI/task metadata uses persisted description when available
The task entry for the resumed agent uses the stored description if present; otherwise a fallback placeholder is used.

### Rewrite requirement
Preserve description continuity for resumed-task UI.

---

## 11.3 Resume preserves output-file/task-output identity
The resumed result points at the same logical task output file derived from the agent identity.

### Rewrite requirement
Preserve stable output-path identity across resume.

---

## 11.4 Resume establishes fresh lifecycle wiring while keeping logical agent identity
The resumed agent gets a new live execution lifecycle (abort controller, task registration, stream wiring), but keeps the same logical persisted identity and transcript.

### Rewrite requirement
Preserve the split between:
- persistent logical agent identity
- fresh runtime execution wiring on resume

---

## 12. Agent resume prompt construction

## 12.1 Resumed prompt stream is “cleaned prior transcript + new user prompt”
The resumed run starts from:
- cleaned resumed sidechain messages
- plus a newly created user message containing the resume prompt

Conceptually:

```ts
promptMessages = [...cleanedResumedMessages, createUserMessage({ content: prompt })]
```

### Rewrite requirement
Preserve this append-new-prompt-on-top-of-cleaned-history construction.

---

## 12.2 Resume does not synthesize a brand-new blank conversation
Even if metadata must be reconstructed, the resumed agent run is fundamentally anchored in the prior transcript.

### Rewrite requirement
Preserve transcript continuity across agent resume.

---

## 13. Discoverability and post-eviction transcript loading

## 13.1 Agent transcripts can be recovered from disk even after in-memory task eviction
The session store can enumerate subagent transcripts directly from the session’s `subagents/` directory rather than relying exclusively on in-memory task state.

### Rewrite requirement
Preserve disk-based subagent transcript discoverability independent of active task memory.

---

## 13.2 In-process teammate transcripts may come from task memory instead of disk
Some in-process teammate/task styles keep their authoritative transcript in task memory rather than in the same stable per-agent disk layout, so the system also knows how to extract those from active task state.

### Rewrite requirement
Preserve support for task-memory-backed teammate transcript extraction where that execution style exists.

---

## 14. Cross-project / worktree session resume relation

## 14.1 Main-session cross-project resume classification informs how a user gets back to the right session
Session resume logic distinguishes:
- same-project resume
- same-repo worktree resume
- completely different project resume

For different projects, it generates a shell command conceptually like:

```bash
cd <projectPath> && pinser --resume <sessionId>
```

For same-repo worktrees, direct resume can be allowed without that cross-project shell handoff.

### Rewrite requirement
Preserve cross-project resume classification and same-repo-worktree special handling.

This is adjacent to agent/worktree resume because both depend on preserving cwd/worktree semantics correctly.

---

## 15. Minimal behavioral interfaces for a rewrite

A compatible rewrite should expose structures roughly like:

```ts
type AgentMetadata = {
  agentType: string
  worktreePath?: string
  description?: string
}

type AgentTranscript = {
  messages: Message[]
  contentReplacements: ContentReplacementRecord[]
}

type ResumeAgentArgs = {
  agentId: string
  prompt: string
  toolUseContext: ToolUseContext
  canUseTool: CanUseToolFn
  invokingRequestId?: string
}

type ResumeAgentResult = {
  agentId: string
  description: string
  outputFile: string
}

type AgentPersistence = {
  setAgentTranscriptSubdir(agentId: string, subdir: string): void
  clearAgentTranscriptSubdir(agentId: string): void
  getAgentTranscriptPath(agentId: AgentId): string

  writeAgentMetadata(agentId: AgentId, metadata: AgentMetadata): Promise<void>
  readAgentMetadata(agentId: AgentId): Promise<AgentMetadata | null>

  getAgentTranscript(agentId: AgentId): Promise<AgentTranscript | null>
  loadSubagentTranscripts(agentIds: string[]): Promise<Record<string, Message[]>>
  loadAllSubagentTranscriptsFromDisk(): Promise<Record<string, Message[]>>

  resumeAgentBackground(args: ResumeAgentArgs): Promise<ResumeAgentResult>
}
```

And for replacement-state reconstruction:

```ts
type SubagentReplacementRecovery = {
  reconstructForSubagentResume(
    parentState: ContentReplacementState | undefined,
    resumedMessages: Message[],
    sidechainRecords: ContentReplacementRecord[],
  ): ContentReplacementState | undefined
}
```

Exact names may differ. The behaviors should not.

---

## 16. Critical invariants for a rewrite

## 16.1 Sidechain transcripts are separate from the main transcript
Failure mode:
- agent messages pollute main-thread history or become non-resumable

## 16.2 Agent type is persisted out-of-band and restored on resume
Failure mode:
- resumed fork silently degrades to generic agent behavior

## 16.3 Resumed fork agents must not receive inherited parent context twice
Failure mode:
- duplicated context, duplicate tool-use IDs, malformed resumes

## 16.4 Resumed fork agents need parent-equivalent system prompt context
Failure mode:
- cache miss, behavior drift, wrong prompt family after resume

## 16.5 Sidechain resume must clean unresolved tool uses / orphaned thinking / whitespace fragments
Failure mode:
- resumed agent transcript is API-invalid

## 16.6 Replacement-state reconstruction must include inherited parent mappings when needed
Failure mode:
- prompt-cache divergence on resumed fork agents

## 16.7 Worktree resume must gracefully fall back if the original worktree is gone
Failure mode:
- resume crashes on missing filesystem state

## 16.8 Resuming a live worktree must defend against stale-worktree cleanup races
Failure mode:
- a just-resumed worktree gets deleted by cleanup logic

## 16.9 Disk-based transcript discovery must work after task eviction
Failure mode:
- old subagent runs disappear from history/inspection despite still being on disk

## 16.10 Resume preserves logical agent identity while rebuilding runtime execution state
Failure mode:
- output paths, task linkage, transcript identity, or UI continuity break

---

## 17. What may vary vs what should stay close

## Preserve closely
- separate sidechain transcript files under session scope
- metadata sidecars with at least `agentType`
- leaf-based sidechain reconstruction by `agentId`
- resumed transcript cleanup before reuse
- worktree-path restoration with graceful fallback
- fork-resume suppression of duplicate inherited context
- parent-system-prompt reuse/reconstruction for fork resumes
- subagent replacement-state reconstruction with inherited gap-fill
- task re-registration on resume
- disk-based subagent transcript discovery

## Can vary somewhat
- exact file naming and subdirectory conventions
- exact async task framework used during resume
- exact fallback/default agent chosen when metadata is missing
- exact mechanism for touching worktree liveness timestamps

---

## 18. Confidence and limits

High confidence:
- the sidechain transcript storage, metadata sidecars, worktree restoration, fork-resume suppression of duplicate context, and replacement-state reconstruction are directly supported by inspected code
- these behaviors clearly encode real operational lessons rather than being incidental design choices

Lower confidence:
- this document focuses on local/background subagent resume and only lightly touches remote-agent restore
- some coordinator/team-specific transcript flows are documented elsewhere and may add more execution-style variants

Even so, this should be a solid clean-room contract for reimplementing subagent persistence, sidechain reconstruction, and background agent resume behavior without copying the original implementation.