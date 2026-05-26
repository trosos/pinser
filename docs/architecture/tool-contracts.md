# Tool contracts and per-tool schema reference

This document records the per-tool contracts that are important to preserve for a clean-room rewrite.

Unless a section explicitly says otherwise, preserve semantic behavior, schemas, and safety invariants rather than byte-exact wording.

It is written so that when it says a behavior must be preserved, the required replacement behavior can be inferred from this document alone rather than from the source implementation.

It focuses only on tools whose implementations were inspected directly in this pass. Where a tool was only observed in the registry and not inspected, it is intentionally omitted here rather than guessed.

Primary inspected sources:
- `src/tools/WebFetchTool/WebFetchTool.ts`
- `src/tools/WebSearchTool/WebSearchTool.ts`
- `src/tools/TaskCreateTool/TaskCreateTool.ts`
- `src/tools/TaskGetTool/TaskGetTool.ts`
- `src/tools/TaskUpdateTool/TaskUpdateTool.ts`
- `src/tools/TaskListTool/TaskListTool.ts`
- `src/tools/TaskStopTool/TaskStopTool.ts`
- `src/tools/ToolSearchTool/ToolSearchTool.ts`
- `src/tools/SkillTool/SkillTool.ts`
- `src/tools/SendMessageTool/SendMessageTool.ts`
- `src/tools/TeamCreateTool/TeamCreateTool.ts`
- `src/tools/TeamDeleteTool/TeamDeleteTool.ts`
- `src/tools/FileWriteTool/FileWriteTool.ts`
- `src/tools/RemoteTriggerTool/RemoteTriggerTool.ts`
- `src/tools/MCPTool/MCPTool.ts`
- `src/tools/ScheduleCronTool/CronCreateTool.ts`
- `src/tools/ScheduleCronTool/CronDeleteTool.ts`
- `src/tools/ScheduleCronTool/CronListTool.ts`
- `src/tools/FileReadTool/prompt.ts` (prompt/contract details only)

---

## 1. Cross-cutting tool contract requirements

These requirements are common across the inspected tools.

### 1.1 Tool definition model
A tool is not only an executable function. A replacement tool system must let each tool provide all of the following kinds of behavior:

- **Identity**: stable tool name, and where applicable aliases
- **Input contract**: a machine-checkable input schema
- **Output contract**: a structured output schema, even if the model-visible rendering is text-only
- **Validation**: input validation that can fail without crashing the turn
- **Permissions**: tool-specific allow/deny/ask behavior
- **Execution**: the side-effecting or read-only runtime logic
- **Concurrency declaration**: whether concurrent execution is safe
- **Read-only/destructive declaration**: whether the tool changes state
- **Progress events**: optional streaming progress updates during a long call
- **Model-visible result mapping**: conversion from internal output object to the `tool_result` content seen by the model
- **App-state side effects**: optional UI/session state changes outside the structured return value

### 1.2 Deferred tool behavior
Some tools are **deferred**. In this system, that means:
- the tool may be absent from the initial prompt-visible tool list
- the tool can still be discovered later by `ToolSearch`
- once selected, the canonical tool name is used for the actual invocation

A clean-room rewrite must preserve this capability for the tools documented here that are marked as deferred.

### 1.3 Non-throwing failures
Several tools intentionally report a normal result object describing failure instead of raising an execution error.

Where this document says a tool has a **non-throwing failure**, the replacement must:
- return a structured result with `success: false` or equivalent documented failure payload
- still produce a normal `tool_result`
- avoid classifying the outcome as a transport/runtime exception

### 1.4 Model-visible result mapping
For many tools, the model-visible `tool_result` text is not a generic JSON serialization of the structured output object.

Where this document specifies exact result text or formatting rules, the rewrite should preserve those formatting rules because model behavior may depend on them.

---

## 2. Task-list tools

These tools operate on the persistent file-backed task-list system documented elsewhere.

## 2.1 `TaskCreateTool`
**File:** `src/tools/TaskCreateTool/TaskCreateTool.ts`

### Purpose
Create a new task in the current persistent task list.

### Enablement and safety
- enabled only when Todo-v2 mode is on
- deferred
- concurrency safe

### Input schema

```ts
{
  subject: string
  description: string
  activeForm?: string
  metadata?: Record<string, unknown>
}
```

### Input field semantics
- `subject`: short task title shown in task summaries
- `description`: detailed description of the work
- `activeForm`: optional present-progressive phrase such as `Implementing parser`
- `metadata`: arbitrary JSON object stored with the task

### Output schema

```ts
{
  task: {
    id: string
    subject: string
  }
}
```

### Required runtime behavior
1. Create a new task record in the current task list.
2. Initialize the new task with:
   - `status: 'pending'`
   - `owner: undefined`
   - `blocks: []`
   - `blockedBy: []`
3. Run task-created hooks after creation.
4. If any blocking task-created hook fails:
   - delete the newly created task
   - fail the tool call by throwing an execution error with the combined hook failure message
5. Update application UI/session state so the tasks view is expanded:
   - `expandedView = 'tasks'`

### Model-visible result
On success, the `tool_result` content should communicate successful task creation, including the created task ID and subject.
A byte-exact string match is not required unless an external integration or test harness explicitly depends on that exact wording.

Illustrative shape:

```text
Task #<id> created successfully: <subject>
```

### Clean-room preservation requirement
A compatible rewrite must preserve the create transaction semantics:
- create first
- run hooks second
- rollback if a blocking hook fails
- expose the created task ID in both structured output and rendered text

---

## 2.2 `TaskGetTool`
**File:** `src/tools/TaskGetTool/TaskGetTool.ts`

### Purpose
Fetch one task by ID from the current task list.

### Enablement and safety
- enabled only when Todo-v2 mode is on
- deferred
- concurrency safe
- read-only

### Input schema

```ts
{
  taskId: string
}
```

### Output schema

```ts
{
  task: {
    id: string
    subject: string
    description: string
    status: 'pending' | 'in_progress' | 'completed'
    blocks: string[]
    blockedBy: string[]
  } | null
}
```

### Required runtime behavior
- Look up the task by `taskId`.
- If found, return the task object.
- If not found, return `{ task: null }`.
- Do not treat a missing task as an execution exception.

### Model-visible result
- If `task === null`, render a human-readable not-found result.
  Illustrative example:

```text
Task not found
```

- If found, render a human-readable multiline summary containing at least:
  - task ID
  - subject
  - status
  - description
  - `blocks`
  - `blockedBy`

The exact prose can vary, but those data fields must be present in the model-visible result.

### Clean-room preservation requirement
The not-found case must remain data-level absence, not a thrown error. A rewrite must preserve both:
- summary listing via `TaskListTool`
- detail fetch via `TaskGetTool`

---

## 2.3 `TaskUpdateTool`
**File:** `src/tools/TaskUpdateTool/TaskUpdateTool.ts`

### Purpose
Update task fields, task status, dependency edges, ownership, and metadata.

### Enablement and safety
- enabled only when Todo-v2 mode is on
- deferred
- concurrency safe

### Input schema

```ts
{
  taskId: string
  subject?: string
  description?: string
  activeForm?: string
  status?: 'pending' | 'in_progress' | 'completed' | 'deleted'
  addBlocks?: string[]
  addBlockedBy?: string[]
  owner?: string
  metadata?: Record<string, unknown>
}
```

### Output schema

```ts
{
  success: boolean
  taskId: string
  updatedFields: string[]
  error?: string
  statusChange?: {
    from: string
    to: string
  }
  verificationNudgeNeeded?: boolean
}
```

### Field semantics
- `subject`, `description`, `activeForm`, `owner`: replace the corresponding task fields
- `status`: changes lifecycle state, with special handling for `'deleted'`
- `addBlocks`: for each listed task ID `X`, add `X` to `thisTask.blocks`
- `addBlockedBy`: for each listed task ID `X`, add `X` to `thisTask.blockedBy`
- `metadata`: merge by key into existing metadata
  - if a provided metadata key has value `null`, delete that key from stored metadata

### Required runtime behavior
1. Expand tasks UI:
   - `expandedView = 'tasks'`
2. If the task does not exist:
   - return a normal structured failure result
   - do not throw
3. Apply normal field updates.
4. If `status === 'deleted'`:
   - delete the task from persistent storage
   - return success immediately
5. If changing status to `'completed'`:
   - run task-completed hooks before finalizing completion
   - if a blocking hook fails, return a normal structured failure result instead of throwing
6. If agent swarms are enabled and all of the following are true:
   - new status is `'in_progress'`
   - request does not provide `owner`
   - task currently has no owner
   then auto-assign the owner to the current agent name
7. If ownership changes in swarm mode, send an assignment mailbox message to the new owner.
8. If the implementation includes the verifier nudge mechanism, preserve it:
   - when a larger task list is being completed without a verification step, set `verificationNudgeNeeded: true`

### Non-throwing failure cases
The following cases must be represented as normal output with `success: false`:
- task not found
- completion blocked by a blocking completion hook

### Model-visible result
- On failure, emit a normal `tool_result`, not an error block.
- On success, include the updated field names in the human-readable text.
- If a teammate completed a task, append a reminder to call `TaskList`.
- If `verificationNudgeNeeded` is true, append a strong reminder to run verification.

### Clean-room preservation requirement
A compatible rewrite must preserve all of the following exact semantics:
- delete-by-setting-`status: 'deleted'`
- metadata merge with `null` meaning delete-key
- non-throwing structured failure for benign update failures
- dependency edge direction:
  - `addBlocks` means “this task blocks those tasks”
  - `addBlockedBy` means “those tasks block this task”

---

## 2.4 `TaskListTool`
**File:** `src/tools/TaskListTool/TaskListTool.ts`

### Purpose
List task summaries from the current task list.

### Enablement and safety
- enabled only when Todo-v2 mode is on
- deferred
- concurrency safe
- read-only

### Input schema

```ts
{}
```

### Output schema

```ts
{
  tasks: Array<{
    id: string
    subject: string
    status: 'pending' | 'in_progress' | 'completed'
    owner?: string
    blockedBy: string[]
  }>
}
```

### Required runtime behavior
- List all tasks from the current task list.
- Exclude tasks whose `metadata._internal` is truthy.
- For each returned task, suppress blockers that are already completed from the returned `blockedBy` list.

### Model-visible result
- If there are no visible tasks, render a human-readable empty-state result.
  Illustrative example:

```text
No tasks found
```

- Otherwise render one line per task in this shape:

```text
#<id> [<status>] <subject> (<owner>) [blocked by #x, #y]
```

Formatting details:
- `(<owner>)` is included only when an owner exists.
- `[blocked by ...]` is included only when the filtered `blockedBy` list is non-empty.

### Clean-room preservation requirement
A rewrite must preserve the distinction between:
- the raw stored task graph
- the filtered summary view shown by `TaskListTool`

Specifically, completed blockers are hidden from summary output even if they still exist historically in storage.

---

## 3. Background task control tool

## 3.1 `TaskStopTool`
**File:** `src/tools/TaskStopTool/TaskStopTool.ts`

### Purpose
Stop a running background task.

### Enablement and compatibility
- deferred
- concurrency safe
- backward-compatible alias: `KillShell`
- for some internal user modes, the user-facing name may be blank; the functional contract remains unchanged

### Input schema

```ts
{
  task_id?: string
  shell_id?: string
}
```

### Input compatibility semantics
- `task_id` is the canonical field
- `shell_id` is deprecated but must still be accepted for backward compatibility
- the effective target ID is:

```ts
targetId = task_id ?? shell_id
```

### Output schema

```ts
{
  message: string
  task_id: string
  task_type: string
  command?: string
}
```

### Validation behavior
The tool must reject the call with a validation error if:
- neither `task_id` nor `shell_id` is provided
- the referenced task does not exist in live app state
- the referenced task is not currently running

### Required runtime behavior
- Stop the running task identified by `targetId`.
- Return a success payload containing:
  - human-readable `message`
  - canonical `task_id`
  - `task_type`
  - optional `command` or task description if available

### Clean-room preservation requirement
A replacement must support both field names during migration and must validate against the live task registry, not only persistent history.

---

## 4. Web tools

## 4.1 `WebFetchTool`
**File:** `src/tools/WebFetchTool/WebFetchTool.ts`

### Purpose
Fetch the contents of a URL and either:
- return fetched markdown directly, or
- apply a caller-provided prompt to the fetched content and return the result

### Enablement and safety
- deferred
- concurrency safe
- read-only
- custom permission logic keyed by destination hostname

### Input schema

```ts
{
  url: string
  prompt: string
}
```

### Input validation
- `url` must parse as a valid absolute URL
- invalid URL input must produce a structured validation failure

### Output schema

```ts
{
  bytes: number
  code: number
  codeText: string
  result: string
  durationMs: number
  url: string
}
```

### Permission behavior
Permission matching for this tool is hostname-based.

For an input URL like:

```text
https://docs.example.com/path/page
```

the normalized permission rule content is:

```text
domain:docs.example.com
```

The tool must support:
- auto-allow for preapproved hosts
- explicit deny rules for a hostname
- explicit ask rules for a hostname
- explicit allow rules for a hostname
- when prompting the user, a suggestion to locally allow the matched hostname

### Required runtime behavior
1. Fetch URL content into a markdown-or-readable-content form.
2. If the fetch resolves via redirect to a **different host** than the originally requested host:
   - do not silently follow through to completion under the original approval context
   - instead return a result instructing the caller to rerun the tool with the redirected URL
3. If the hostname is preapproved and fetched markdown length is below the configured passthrough threshold, return raw markdown directly in `result`.
4. Otherwise apply the caller-provided `prompt` to the fetched content and return the prompt-processed result in `result`.
5. If the fetched resource is binary and the implementation persists it to disk, append a human-readable note to `result` containing:
   - the persisted local path
   - the size

### Model-visible result
The `tool_result` content is exactly `output.result` and nothing else.

### Clean-room preservation requirement
A replacement must preserve all three distinct execution modes:
- same-host direct fetch with raw markdown passthrough
- prompt-applied content processing
- cross-host redirect refusal requiring explicit rerun

---

## 4.2 `WebSearchTool`
**File:** `src/tools/WebSearchTool/WebSearchTool.ts`

### Purpose
Search the web using provider-backed server-tool search support.

### Enablement
The tool is available only under the following provider/model rules:
- `firstParty`: enabled
- `vertex`: enabled only for Claude 4 family models
- `foundry`: enabled
- all other provider/model combinations: disabled

### Input schema

```ts
{
  query: string
  allowed_domains?: string[]
  blocked_domains?: string[]
}
```

### Input validation
- `query.length >= 2`
- `allowed_domains` and `blocked_domains` are mutually exclusive

### Output schema

```ts
{
  query: string
  results: Array<
    | string
    | {
        tool_use_id: string
        content: Array<{
          title: string
          url: string
        }>
      }
  >
  durationSeconds: number
}
```

### Permission behavior
- permission mode is passthrough for execution
- permission suggestions may still recommend allowing the tool generally

### Required runtime behavior
1. Invoke the model query path with an extra server-tool schema equivalent to:
   - `web_search_20250305`
2. Optionally use a smaller fast model if the controlling feature flag says to do so.
3. During streaming execution, emit progress updates for:
   - search query construction/updates inferred from partial JSON deltas
   - result arrival, including result counts when available
4. Produce a final structured output whose `results` array may mix:
   - plain commentary strings
   - structured hit groups with a `tool_use_id` and `content` array of `{ title, url }`

### Model-visible result
The `tool_result` text must include all of the following:
- the original search query
- any commentary strings returned by the tool flow
- the discovered links/hit groups in a readable form
- a final reminder that sources must be cited as markdown hyperlinks

### Clean-room preservation requirement
A compatible rewrite must preserve:
- the provider/model gating table above
- mixed string + structured-hit result shape
- streamed progress during search execution
- explicit citation reminder in the final rendered result

---

## 5. Search and discovery tools

## 5.1 `ToolSearchTool`
**File:** `src/tools/ToolSearchTool/ToolSearchTool.ts`

### Purpose
Search the deferred tool catalog and return tool references that can be selected for later use.

### Enablement and safety
- enabled when optimistic tool-search mode says the feature may be available
- concurrency safe
- read-only

### Input schema

```ts
{
  query: string
  max_results?: number
}
```

### Input defaults
- if omitted, `max_results = 5`

### Output schema

```ts
{
  matches: string[]
  query: string
  total_deferred_tools: number
  pending_mcp_servers?: string[]
}
```

### Mode A: direct selection syntax
The tool must recognize the following query syntax:

```text
select:<tool_name>
select:<tool_a>,<tool_b>,<tool_c>
```

#### Direct selection behavior
- Parse the comma-separated list after `select:`.
- For each requested name:
  1. first try exact or canonical resolution inside deferred tools
  2. if not found there, try the full tool set
- Return the canonical names of all found tools in `matches`.
- Partial success is allowed: missing names do not invalidate found names.

### Mode B: keyword search
If `query` does not start with `select:`, perform keyword search.

#### Keyword search corpus
Search only the deferred tool set.

#### Keyword scoring sources
Score candidate tools using the following searchable text sources:
- exact tool-name parts
- MCP server name and action-name parts
- substring matches in tool names
- `searchHint`
- prompt text
- description text

#### Required-term syntax
A token prefixed with `+` means that token is required.
Example:

```text
+search code review
```

A tool that does not match `search` must not be returned.

#### Pending MCP hint behavior
If there are no matches and some MCP servers are still connecting, the output may include:

```ts
pending_mcp_servers: string[]
```

listing those still-pending servers.

### Model-visible result
- If no matches are found, render explanatory text, optionally mentioning pending MCP servers.
- If matches are found, render them as **tool references**, not plain freeform text.

A compatible rewrite therefore needs a model-visible result type equivalent to a “tool reference block”.

### Clean-room preservation requirement
A rewrite must preserve all of the following inferable behavior:
- `select:` is a special control syntax, not just a search string
- direct selection can return multiple tools
- keyword search searches deferred tools only
- required-term `+token` syntax is supported
- no-match results may mention pending MCP server names

---

## 6. Skill tool

## 6.1 `SkillTool`
**File:** `src/tools/SkillTool/SkillTool.ts`

### Purpose
Invoke a slash-command skill either:
- inline in the current conversation, or
- in a forked sub-agent

### Input schema

```ts
{
  skill: string
  args?: string
}
```

### Output schema
The output is a tagged union.

#### Inline result shape
```ts
{
  success: boolean
  commandName: string
  allowedTools?: string[]
  model?: string
  status?: 'inline'
}
```

#### Forked result shape
```ts
{
  success: boolean
  commandName: string
  status: 'forked'
  agentId: string
  result: string
}
```

### Input normalization and validation
- trim `skill`
- if it begins with `/`, remove the leading slash before command lookup
- reject if the command does not exist
- reject if the command is not a prompt-based command
- reject if the command has `disableModelInvocation`
- if the experimental remote canonical skill feature is enabled, also allow `_canonical_<slug>` references

### Permission behavior
Permission matching is skill-name based.

Supported rule forms:
- exact skill name, such as:

```text
fix-tests
```

- wildcard prefix form:

```text
fix-tests:*
```

Behavior to preserve:
- deny rules checked first
- allow rules can match exact name or prefix rule
- some safe skills may auto-allow
- remote canonical skills may auto-allow after deny checks
- default unresolved state is `ask`

### Execution path A: remote canonical skill
If the feature remains in the rewrite, preserve these semantics:
- remote skill content is loaded from a remote `SKILL.md` source
- the loaded content is injected as a meta user message
- the invoked skill is recorded so it can be preserved across compaction

### Execution path B: forked skill
When a prompt command declares `context === 'fork'`, the tool must:
- run the skill in a sub-agent
- stream progress from that fork, including assistant/user/tool-use events from the fork when available
- return a forked result object with:
  - `status: 'forked'`
  - `agentId`
  - final extracted text in `result`

### Execution path C: inline skill
When the command runs inline, the tool may:
- append `newMessages` into the current conversation
- temporarily extend allowed tools
- override the main-loop model
- override effort

A rewrite therefore needs a way for a tool call to return both:
- a primary structured result
- transient context modifications affecting the remainder of the turn

### Model-visible result
- forked path: the `tool_result` text is the final fork result text
- inline path: the `tool_result` text is exactly:

```text
Launching skill: <commandName>
```

### Clean-room preservation requirement
A compatible rewrite must preserve:
- leading slash compatibility
- inline vs forked distinction
- ability for a tool to modify subsequent turn context
- exact/prefix skill permission rules

---

## 7. Multi-agent and swarm tools

## 7.1 `SendMessageTool`
**File:** `src/tools/SendMessageTool/SendMessageTool.ts`

### Purpose
Send messages between teammates, local agents, peer sessions, and supported external bridge/socket endpoints.

### Enablement
- enabled only when agent swarms are enabled
- deferred
- read-only only when `message` is a plain string
- if `message` is a structured control message, the call is not considered read-only

### Input schema

```ts
{
  to: string
  summary?: string
  message:
    | string
    | { type: 'shutdown_request'; reason?: string }
    | {
        type: 'shutdown_response'
        request_id: string
        approve: boolean
        reason?: string
      }
    | {
        type: 'plan_approval_response'
        request_id: string
        approve: boolean
        feedback?: string
      }
}
```

### Addressing model
The `to` field supports these address families:
- teammate name, for example `alice`
- broadcast, exactly `*`
- bridge route, prefixed with `bridge:`
- UDS route, prefixed with `uds:`
- validated raw local agent ID where supported

The user-facing contract excludes `@name` syntax; bare names are required.

### Validation rules
- `to` must be non-empty
- `bridge:` and `uds:` targets must include a non-empty destination after the prefix
- teammate names must be bare names; `@alice` is invalid
- plain string messages usually require `summary`
  - exception: some UDS cases may omit it
- structured messages cannot be broadcast to `*`
- structured messages cannot be sent to `bridge:` or `uds:` routes
- a `shutdown_response` must target `team-lead`
- if `shutdown_response.approve === false`, `reason` is required

### Structured control message protocol
The rewrite must preserve this exact union of structured control messages:

#### Shutdown request
```ts
{ type: 'shutdown_request'; reason?: string }
```

#### Shutdown response
```ts
{
  type: 'shutdown_response'
  request_id: string
  approve: boolean
  reason?: string
}
```

#### Plan approval response
```ts
{
  type: 'plan_approval_response'
  request_id: string
  approve: boolean
  feedback?: string
}
```

### Permission behavior
- sending across a cross-machine bridge route requires explicit user approval
- this approval requirement must not be bypassed by normal auto-allow settings

### Routing behavior
A compatible rewrite must preserve the following routing table.

#### Route A: `bridge:<destination>`
- plain text only
- requires an active REPL bridge/session bridge
- forwards via the cross-session bridge send path

#### Route B: `uds:<destination>`
- plain text only
- forwards via the UDS socket send path

#### Route C: local agent / in-process teammate
- resolves a local running agent by registered name or valid raw agent ID
- if the local agent is running, queue the message for that agent
- if the local agent is stopped but resumable, attempt transcript-based auto-resume before delivery

#### Route D: broadcast `*`
- plain text only
- send to all teammates except the sender

#### Route E: direct teammate mailbox
- plain text only
- write the message to the target teammate mailbox

#### Route F: structured control messages
- only valid for local team routing, not bridge or UDS
- supports shutdown request/response and plan approval response handling
- shutdown approval may hard-abort in-process controllers
- non-in-process shutdown falls back to graceful shutdown path
- plan-approval responses inherit the permission mode expected by the receiver flow

### Output families
A rewrite must provide enough output structure to distinguish at least:
- direct plain-text send success
- broadcast success
- structured request sent
- structured response sent

The exact field names may vary if the system is internal-only, but these outcome categories must remain distinguishable.

### Clean-room preservation requirement
A replacement must preserve:
- the addressing model above
- the control-message union above
- summary requirement for plain text messages
- bridge approval safety gate
- stopped-local-agent auto-resume attempt on incoming message

---

## 7.2 `TeamCreateTool`
**File:** `src/tools/TeamCreateTool/TeamCreateTool.ts`

### Purpose
Create a team/swarm context and switch task-list routing into that team context.

### Enablement
- enabled only when agent swarms are enabled
- deferred

### Input schema

```ts
{
  team_name: string
  description?: string
  agent_type?: string
}
```

### Output schema

```ts
{
  team_name: string
  team_file_path: string
  lead_agent_id: string
}
```

### Required runtime behavior
1. Refuse creation if the current leader already manages a team.
2. If `team_name` already exists, generate a unique replacement team slug and use that instead.
3. Compute a deterministic lead agent ID from the final sanitized team name.
4. Write a persistent team file and return its path as `team_file_path`.
5. Register the team for session cleanup on exit.
6. Reset and create the task-list directory associated with the new team.
7. Set the leader’s active team name so task APIs route to the team task list instead of the default session task list.
8. Materialize the team context into application state.
9. Emit the corresponding telemetry event if telemetry remains.

### Clean-room preservation requirement
A compatible rewrite must preserve the coupling between:
- team creation
- team identity persistence
- team-scoped task-list initialization
- task routing into that team context

---

## 7.3 `TeamDeleteTool`
**File:** `src/tools/TeamDeleteTool/TeamDeleteTool.ts`

### Purpose
Delete the current team/swarm context and clean up all associated session state.

### Enablement
- enabled only when agent swarms are enabled
- deferred

### Input schema

```ts
{}
```

### Output schema

```ts
{
  success: boolean
  message: string
  team_name?: string
}
```

### Required runtime behavior
1. Read the current persisted team file.
2. Inspect remaining team members.
3. Refuse deletion if any non-lead teammate is still active.
   - members marked `isActive === false` count as inactive and do not block deletion
4. Delete team directories and related persisted team state.
5. Unregister the team from session-cleanup tracking.
6. Clear teammate color assignments.
7. Clear the leader’s active team name.
8. Clear team context and inbox from application state.

### Clean-room preservation requirement
Deletion must remain blocked by active non-lead members. This behavior is part of the external coordination contract, not just an implementation detail.

---

## 8. File tools

## 8.1 `FileWriteTool`
**File:** `src/tools/FileWriteTool/FileWriteTool.ts`

### Purpose
Create a new file or replace an existing file’s entire contents.

### Safety and behavior flags
- strict input handling
- write-capable/destructive
- custom path-based permission matching
- custom rejected/error/result rendering

### Input schema

```ts
{
  file_path: string
  content: string
}
```

### Input validation
- `file_path` must be absolute
- path expansion occurs before the rest of validation
- writes to protected team-memory secret paths are rejected
- denied paths from permission settings are rejected
- UNC paths may defer certain checks to the permission layer without local filesystem probing

### Existing-file preconditions
If the target file already exists, all of the following must be true before overwrite:
- the file has been read previously in this session
- the prior read was not partial
- the file has not changed since that read

If any of these conditions fail, the tool must not overwrite the file.

### Output schema

```ts
{
  type: 'create' | 'update'
  filePath: string
  content: string
  structuredPatch: Hunk[]
  originalFile: string | null
  gitDiff?: ToolUseDiff
}
```

### Output field semantics
- `type`: `'create'` if the file did not previously exist, else `'update'`
- `filePath`: final resolved absolute path written
- `content`: exact content written
- `structuredPatch`: diff hunks describing the change
- `originalFile`: previous full content, or `null` for create
- `gitDiff`: optional VCS diff object if that integration is enabled

### Required runtime behavior
1. Resolve and validate the path.
2. Ensure the parent directory exists.
3. Re-check staleness immediately before writing.
4. Write atomically.
5. Preserve the exact line endings contained in the caller-provided `content` string.
   - do not normalize to the file’s previous newline style
6. Update read-file cache state to reflect the new content.
7. Notify file-integrated subsystems that still exist in the rewrite, such as:
   - file history tracking
   - diagnostics/LSP
   - editor integration
8. Return create/update result plus patch metadata.

### Model-visible result
- create:

```text
File created successfully at: <path>
```

- update:

```text
The file <path> has been updated successfully.
```

### Clean-room preservation requirement
A compatible rewrite must preserve the must-read-before-write invariant and the stale-file check. Those are central safety properties, not optional UX details.

---

## 8.2 `Read` tool contract notes
**Source observed:** `src/tools/FileReadTool/prompt.ts`

The full implementation was not inspected in this pass, but the externally visible contract from the prompt text is strong enough to specify the replacement behavior.

### Tool name
```text
Read
```

### Required input behavior
- file path must be absolute
- supports optional line offset and line limit
- default maximum lines per read is `2000`

### Required output behavior
- text output is rendered with 1-based line numbers in a `cat -n`-style format
- images can be read visually
- PDFs can be read; for large PDFs the caller must specify a page range when PDF support is enabled
- Jupyter notebooks can be read as structured notebook content including cells and outputs
- directories are not readable through this tool; directory listing must be done through shell/listing tools
- empty files should not return silent blank output; they must include a warning/reminder indicating the file is empty

### Unchanged-file stub behavior
The implementation includes a reusable unchanged-file stub message. A compatible rewrite should preserve an equivalent visible behavior:

```text
File unchanged since last read... refer to earlier Read tool_result
```

### Clean-room preservation requirement
Even if the backend implementation changes completely, the replacement `Read` tool must preserve the user/model-visible semantics above.

---

## 9. Cron and scheduled-task tools

## 9.1 `CronCreateTool`
**File:** `src/tools/ScheduleCronTool/CronCreateTool.ts`

### Purpose
Create a scheduled one-shot or recurring prompt job.

### Enablement
- enabled only when Kairos cron mode is on
- deferred

### Input schema

```ts
{
  cron: string
  prompt: string
  recurring?: boolean
  durable?: boolean
}
```

### Output schema

```ts
{
  id: string
  humanSchedule: string
  recurring: boolean
  durable?: boolean
}
```

### Validation behavior
The tool must reject creation if any of the following are true:
- the cron expression is invalid
- the cron expression cannot produce a next run within the next year
- the global scheduled job count is already at the maximum of `50`
- the caller is a teammate and requests `durable: true`

### Required runtime behavior
- if the durable-cron feature gate is off, force `durable = false` even if requested
- persist the cron task
- enable scheduled-task polling in the current session so the new job can run

### Model-visible result
The final `tool_result` text must communicate all of the following:
- job ID
- human-readable schedule
- whether the job is recurring or one-shot
- whether the job is durable/persisted or session-only

Exact prose may vary, but all four pieces of information must remain present.

### Clean-room preservation requirement
A compatible rewrite must preserve:
- teammate prohibition on durable cron creation
- hard global cap of 50 jobs
- distinction between session-only and durable jobs

---

## 9.2 `CronDeleteTool`
**File:** `src/tools/ScheduleCronTool/CronDeleteTool.ts`

### Purpose
Delete one scheduled job.

### Input schema

```ts
{
  id: string
}
```

### Output schema

```ts
{
  id: string
}
```

### Validation behavior
Reject the call if:
- the job does not exist
- the caller is a teammate attempting to delete a job not owned by that teammate

### Required runtime behavior
- remove the specified job from storage/scheduler state

### Model-visible result
The `tool_result` text must be exactly:

```text
Cancelled job <id>.
```

---

## 9.3 `CronListTool`
**File:** `src/tools/ScheduleCronTool/CronListTool.ts`

### Purpose
List visible scheduled jobs.

### Input schema

```ts
{}
```

### Output schema

```ts
{
  jobs: Array<{
    id: string
    cron: string
    humanSchedule: string
    prompt: string
    recurring?: boolean
    durable?: boolean
  }>
}
```

### Visibility rules
- team lead can see all jobs
- a teammate can see only jobs whose owner/agent association matches that teammate’s `agentId`

### Model-visible result
- if there are no visible jobs:

```text
No scheduled jobs.
```

- otherwise each listed job must expose at least:
  - ID
  - human-readable schedule
  - recurring vs one-shot
  - durable vs session-only
  - a truncated form of the prompt

### Clean-room preservation requirement
A rewrite must preserve teammate scoping and the durable/session-only distinction in both structured and rendered outputs.

---

## 10. Team and integration tools

## 10.1 `MCPTool`
**File:** `src/tools/MCPTool/MCPTool.ts`

### Purpose
Provide the base built-in adapter shape for tools supplied by MCP servers.

### Input schema
```ts
Record<string, unknown>
```

### Output schema
```ts
string
```

### Required behavior
- the tool participates in the same tool abstraction as built-in tools
- `isMcp`-equivalent metadata must identify it as MCP-backed
- name, description, prompt, and call behavior are supplied/overridden from the connected MCP tool definition rather than hard-coded in the base class
- permission mode is passthrough unless the surrounding system applies additional policy
- result truncation is evaluated line-by-line

### Clean-room preservation requirement
A rewrite must preserve the fact that MCP-provided tools are first-class members of the unified tool system rather than a separate side channel.

---

## 10.2 `RemoteTriggerTool`
**File:** `src/tools/RemoteTriggerTool/RemoteTriggerTool.ts`

### Purpose
Act as a tool-level multiplexer over the remote trigger HTTP API.

### Enablement and safety
- enabled only when the `tengu_surreal_dali` feature flag is on
- enabled only when policy `allow_remote_sessions` allows it
- deferred
- concurrency safe
- read-only if and only if `action` is `'list'` or `'get'`

### Input schema

```ts
{
  action: 'list' | 'get' | 'create' | 'update' | 'run'
  trigger_id?: string
  body?: Record<string, unknown>
}
```

### Output schema

```ts
{
  status: number
  json: string
}
```

### Action multiplexer contract
The tool’s required behavior is fully determined by `action` as follows:

#### Action `list`
- input shape:

```ts
{ action: 'list' }
```

- validation: no additional fields required
- HTTP dispatch:

```http
GET /v1/code/triggers
```

- read-only: yes

#### Action `get`
- input shape:

```ts
{ action: 'get', trigger_id: string }
```

- validation:
  - `trigger_id` is required
- HTTP dispatch:

```http
GET /v1/code/triggers/{trigger_id}
```

- read-only: yes

#### Action `create`
- input shape:

```ts
{ action: 'create', body: Record<string, unknown> }
```

- validation:
  - `body` is required
- HTTP dispatch:

```http
POST /v1/code/triggers
```

- read-only: no

#### Action `update`
- input shape:

```ts
{ action: 'update', trigger_id: string, body: Record<string, unknown> }
```

- validation:
  - `trigger_id` is required
  - `body` is required
- HTTP dispatch:

```http
POST /v1/code/triggers/{trigger_id}
```

- read-only: no

#### Action `run`
- input shape:

```ts
{ action: 'run', trigger_id: string }
```

- validation:
  - `trigger_id` is required
- HTTP dispatch:

```http
POST /v1/code/triggers/{trigger_id}/run
Body: {}
```

- read-only: no

### Shared runtime behavior
> **Internal Anthropic API note**
> The `/v1/code/triggers...` surface described here should be treated as **internal Anthropic API**.
> Preserve it only for compatibility; do not present it as stable public Claude API.

For all actions:
- refresh OAuth token if needed before sending the request
- send the authenticated request to the remote trigger API
- return:

```ts
{
  status: <http status code>,
  json: <JSON-stringified response body>
}
```

### Model-visible result
The `tool_result` text must be exactly this shape:

```text
HTTP <status>
<json>
```

where `<json>` is the string stored in the structured output’s `json` field.

### Clean-room preservation requirement
This section fully specifies the tool’s multiplexer shape. A compatible rewrite must preserve the input variants, required fields, HTTP mapping, and read-only classification exactly as documented above.

---

## 11. Preservation checklist

If these tools are reimplemented, preserve at minimum:

- stable tool names and documented aliases
- the exact input and output schemas listed here
- explicitly documented validation vs execution-failure distinctions
- non-throwing failure cases where documented
- documented `tool_result` text shapes
- app-state side effects documented here for task/team tools
- streamed progress behavior documented here for `WebSearchTool` and `SkillTool`
- documented address-routing behavior for `SendMessageTool`
- direct-selection and keyword-search behavior for `ToolSearchTool`
- the `RemoteTriggerTool` action table exactly as specified above

---

## 12. Additional core-tool contracts

This section closes the biggest practical coverage gaps by consolidating the externally important contracts for the remaining high-usage tool families.

Where these contracts were already verified in companion docs, this section restates them in one tool-catalog document so implementation teams do not need to reconstruct the core tool surface from several files.

Unless explicitly marked otherwise, wording examples in this section are illustrative rather than normative.

---

## 12.1 `Read`
**Primary companion sources:**
- `docs/implementation-notes-and-gotchas.md`
- `docs/path-and-filesystem-safety.md`
- `src/tools/FileReadTool/prompt.ts` (already cited earlier in this document)

### Purpose
Read file contents or file-like content in a model-consumable form.

### Required input behavior
A compatible rewrite must preserve:
- absolute-path input semantics
- optional offset/range behavior for partial reads
- a default maximum read window of `2000` lines when the caller does not request a narrower window

### Required output behavior
A compatible rewrite must preserve all of the following user/model-visible behaviors:
- text results rendered with 1-based line numbers in a `cat -n`-style layout
- directories rejected rather than treated as readable files
- empty files producing an explicit empty-file indication rather than silent blank output
- images readable through a visual/attachment-aware path when supported
- PDFs readable, with page-range expectations for large files where PDF support exists
- Jupyter notebooks readable as notebook structure rather than raw JSON text when notebook support is active

### Safety invariants
A compatible rewrite must preserve:
- unsafe special-file blocking for things like device files and stdio aliases
- UNC/network-path prevalidation before filesystem probing on Windows-like environments
- unchanged-file de-dup behavior or an equivalent optimization that avoids re-inlining identical content repeatedly

### Mutation interaction invariant
A prior read only authorizes later mutation if it was a full read of the file rather than a partial range read.
That distinction is part of the editing safety model and must remain stable.

---

## 12.2 `Edit`
**Primary companion sources:**
- `docs/implementation-notes-and-gotchas.md`
- `docs/path-and-filesystem-safety.md`

### Purpose
Apply text edits to an existing non-notebook file.

### Required behavior
A compatible rewrite must preserve:
- absolute-path handling
- notebook rejection for `.ipynb` targets, which must be routed to `NotebookEdit`
- read-before-write enforcement
- rejection when the file was only partially read earlier in the session
- stale-read protection before mutation
- content-comparison fallback for unreliable mtime-only staleness checks on Windows

### Safety invariants
The rewrite must preserve the editing contract that a model cannot safely patch a file it has not fully seen in-session or whose contents may have changed since that read.

### Output expectations
The exact phrasing of success text is not the important compatibility surface here.
What matters is that the tool returns a normal tool result carrying:
- the resolved target file
- enough patch/change information for transcript/UI presentation
- failure as a normal validation/tool outcome where appropriate rather than a crash

---

## 12.3 `Bash`
**Primary companion source:**
- `docs/bash-and-powershell-safety.md`

### Purpose
Execute shell commands with permission checks, read-only classification, sandbox routing, and background-task support.

### Canonical input shape
```ts
{
  command: string
  timeout?: number
  run_in_background?: boolean
  dangerouslyDisableSandbox?: boolean
}
```

### Required behavioral contract
A compatible rewrite must preserve all of the following:
- per-command sandbox routing
- explicit but policy-controlled `dangerouslyDisableSandbox`
- exact/prefix/wildcard permission matching semantics
- stronger normalization for deny/ask matching than allow matching
- AST-first or equivalently structured parsing with fail-safe degradation
- subcommand-aware handling of compound commands
- argument-sensitive read-only classification
- validation of redirected output targets
- git/hook/bare-repo hardening
- `cd` plus `git` special handling
- stable background-task identity and output retrieval for backgrounded jobs

### Backgrounding contract
The rewrite must preserve:
- explicit background execution
- automatic backgrounding where supported by policy/runtime behavior
- continuity of task identity/output when a foreground command becomes backgrounded

### Compatibility note
This document defers all detailed safety matrices to `docs/bash-and-powershell-safety.md`, which is the normative shell-safety reference.

---

## 12.4 `Glob`
**Primary companion sources:**
- `docs/implementation-notes-and-gotchas.md`
- `docs/path-and-filesystem-safety.md`

### Purpose
Enumerate files by glob pattern without requiring shell expansion.

### Required behavioral contract
A compatible rewrite must preserve:
- path-based safety validation before filesystem access where required
- UNC/network-path prevalidation before probing remote paths on Windows-like environments
- operation over the allowed workspace/path scope rather than unrestricted host traversal
- normal tool-result output listing matched files in a deterministic, readable form

### Safety note
The important compatibility surface is not specific library choice; it is safe path handling, predictable enumeration, and avoiding premature probing of dangerous network paths.

---

## 12.5 `Grep`
**Primary companion sources:**
- `docs/implementation-notes-and-gotchas.md`
- `docs/path-and-filesystem-safety.md`

### Purpose
Search file contents by regex/pattern across a file set.

### Required behavioral contract
A compatible rewrite must preserve:
- path-scope enforcement and safe prevalidation of search roots
- UNC/network-path prevalidation before filesystem probing on Windows-like environments
- readable result rendering that includes match context/location information
- safe handling of large result sets through truncation, limits, or equivalent budgeting behavior

### Compatibility note
The exact grep engine may change, but safe path handling and readable structured match reporting must remain.

---

## 12.6 `NotebookEdit`
**Primary companion sources:**
- `docs/implementation-notes-and-gotchas.md`
- notebook-related references in file-tool safety docs

### Purpose
Apply structured edits to Jupyter notebooks.

### Required behavioral contract
A compatible rewrite must preserve:
- notebook mutation occurring through a notebook-specific tool rather than generic text edit
- read-before-write enforcement for notebooks
- stale-read protection for notebooks
- cell-oriented edit operations rather than blind raw-JSON patching as the model-facing contract

### Compatibility note
The exact edit schema can evolve, but the rewrite must preserve notebook-specific semantics and safety invariants.

---

## 12.7 `LSP`
**Primary companion sources:**
- `docs/interfaces-and-endpoints.md`
- `docs/implementation-notes-and-gotchas.md`

### Purpose
Expose language-server queries such as symbol lookup, references, definitions, hover, and diagnostics.

### Required behavioral contract
A compatible rewrite must preserve an action-oriented interface equivalent to:
- symbols
- references
- diagnostics
- definition
- hover

### Required semantics
The rewrite must preserve:
- path-aware language-service lookup
- normal tool-result responses instead of ad hoc side channels
- safe path handling before workspace probing, including UNC/network-path caution where relevant
- compatibility with the unified tool abstraction rather than a UI-only feature path

---

## 12.8 `Agent` / delegate-or-spawn tool
**Primary companion sources:**
- `docs/task-and-swarm.md`
- `docs/interfaces-and-endpoints.md`
- `docs/agent-resume-and-sidechains.md`

### Purpose
Spawn or delegate work to a subagent/teammate and return enough identity information for later coordination.

### Required behavioral contract
A compatible rewrite must preserve:
- explicit delegated prompt input
- optional model/system-prompt control for the spawned worker when supported
- app-state-visible task registration for spawned work
- stable agent/task identity for later messaging and lifecycle control
- message-oriented rather than shared-memory coordination semantics
- distinction between graceful termination and hard kill for delegated execution

### Compatibility note
This tool family sits on top of the executor/swarm contract documented in `docs/task-and-swarm.md`; that document is the normative orchestration reference.

---

## 12.9 MCP resource and auth tools
**Primary companion sources:**
- `docs/interfaces-and-endpoints.md`
- `docs/tool-contracts.md` section on `MCPTool`

### Purpose
Support interaction with connected MCP servers beyond plain built-in tools, including:
- listing server resources
- reading a selected resource by URI
- authenticating to a server when required
- invoking MCP tools through the unified tool system

### Required behavioral contract
A compatible rewrite must preserve:
- MCP-backed capabilities as first-class participants in the unified tool system
- stable distinction between listing resources, reading a resource, authenticating, and invoking an MCP tool
- server-qualified addressing where needed
- normal tool results rather than hidden side-channel behavior

### Authentication semantics
A rewrite must preserve the existence of an explicit authentication path for MCP servers that require OAuth or credentials.
Do not assume MCP access is always anonymous or pre-authorized.

---

## 13. Remaining gaps

After the additions above, the remaining gaps are mostly lower-level implementation specifics rather than missing top-level tool families.

Possible future follow-up work:
- deeper per-field schema extraction for any still-uninspected tool implementation files
- more detailed result-rendering examples where external compatibility truly depends on exact formatting
- additional MCP-server-specific contract detail if those integrations become a delivery priority

