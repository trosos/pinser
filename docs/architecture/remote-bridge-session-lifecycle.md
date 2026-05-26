# Remote/bridge session lifecycle and transport invariants for a clean-room rewrite

This document captures the lifecycle, transport semantics, state ownership, and failure/recovery invariants for the remote-control / bridge subsystem.

> **Internal Anthropic API note**
> The bridge/session transport internals and lifecycle semantics described here should be treated as **internal Anthropic API / internal protocol behavior**.
> Preserve them only for compatibility with this codepath; do not present them as stable public Claude API surface.

It is written as a clean-room behavioral spec, not as a code tour.

Primary inspected sources for this pass:
- `src/bridge/types.ts`
- `src/bridge/bridgeApi.ts`
- `src/bridge/workSecret.ts`
- `src/bridge/bridgeMain.ts`
- `src/bridge/sessionRunner.ts`
- `src/bridge/replBridge.ts`
- `src/cli/remoteIO.ts`
- `src/cli/structuredIO.ts`
- `src/cli/transports/HybridTransport.ts`
- `src/cli/transports/SSETransport.ts`

Companion docs:
- `docs/transcript-and-persistence-semantics.md`
- `docs/session-compaction-and-recovery.md`
- `docs/agent-resume-and-sidechains.md`
- `docs/message-normalization-for-api.md`
- `docs/permission-engine.md`
- `docs/tool-input-streaming-and-partial-assembly.md`

---

## 1. Scope

This document covers the remote-control bridge as a **distributed lifecycle** composed of:
- environment registration
- work polling
- work acknowledgment
- session spawn/attach
- child transport establishment
- permission/control event round-tripping
- heartbeat / lease extension
- reconnect / redispatch behavior
- session archival and environment deregistration

It covers both major child transport modes:
- **v1 session-ingress**: WebSocket/SSE-like read path plus POST write path behavior as used by bridge child sessions
- **CCR v2 / code sessions**: SSE read + POST write + worker registration/epoch semantics

It also covers the single-process REPL bridge shape enough to preserve shared invariants.

It does **not** try to fully document:
- the web product UX
- every bridge UI rendering detail
- the entire daemon-side architecture behind the remote APIs

---

## 2. Mental model

The bridge is not just “a remote socket.”

It is a coordination layer with at least four independently failing state domains:
1. the **registered environment** on the server
2. the **leased work item** representing a session assignment
3. the **child CLI process** executing the session locally
4. the **session transport connection** carrying structured control/data events

A correct rewrite must preserve the fact that these domains are related but not identical.

### Rewrite requirement
Do not collapse environment, work item, session process, and transport into one lifecycle object with one boolean state.

---

## 3. Core entities and their identities

A compatible rewrite should preserve these distinct identity classes.

## 3.1 Environment identity
An environment is the server-side registration for a bridge instance.

Relevant properties:
- server-issued `environment_id`
- secret used for environment-scoped operations
- metadata such as machine name, directory, branch, worker type, and capacity

### Behavioral role
The environment is the server-visible container that can poll for work and be shown as online/offline.

---

## 3.2 Work identity
A work item is a leased assignment delivered to an environment.

Relevant properties:
- `work.id`
- `work.data.type`
- `work.data.id` for session work
- lease/heartbeat state

### Behavioral role
Work is what gets polled, acknowledged, heartbeated, and stopped.

A session can exist conceptually beyond a single work-delivery attempt.

---

## 3.3 Session identity
A session identity is distinct from work identity and may appear in multiple wire formats.

The implementation distinguishes at least:
- infra-flavored IDs
- compat/user-facing IDs

### Rewrite requirement
Preserve session-ID compatibility handling rather than assuming one canonical string format everywhere.

---

## 3.4 Transport sequence identity
For SSE-based transports, transport continuity is tracked with a sequence-number high-water mark.

### Behavioral role
This sequence number is not the same as session identity. It is a transport resume cursor.

### Rewrite requirement
Preserve a distinct transport resume cursor for event-stream reconnection.

---

## 4. Environment registration lifecycle

## 4.1 Environment registration is explicit and server-authoritative
The bridge first registers an environment and receives:
- `environment_id`
- `environment_secret`

The server-issued ID must then be treated as authoritative, even if the client provided an idempotency/reuse hint.

### Rewrite requirement
Preserve server-authoritative environment identity after registration.

---

## 4.2 Registration payload includes capacity and origin metadata
Environment registration includes operational metadata such as:
- machine name
- working directory
- branch
- repository URL
- maximum concurrent sessions
- worker-type/origin metadata

### Rewrite requirement
Preserve registration-time advertisement of capacity and worker origin.

This is not cosmetic; it affects server-side picker/filtering behavior and admission semantics.

---

## 4.3 Re-registration can reuse an existing environment ID when resuming
A reconnecting bridge may provide a previously issued backend `environment_id` so the backend can reattach instead of creating a fresh environment.

### Rewrite requirement
Preserve explicit re-registration/reuse semantics for resumable bridge instances.

---

## 4.4 Registration auth and poll auth are not the same thing conceptually
Some bridge API calls use the environment secret or OAuth-level auth; others use a session-ingress token/JWT.

### Rewrite requirement
Preserve separate auth classes for:
- environment management
- work lease actions
- session transport / session event actions

---

## 5. Work polling lifecycle

## 5.1 Polling is long-lived and normal no-work responses are first-class
Polling can legitimately return “no work” repeatedly without implying failure.

### Rewrite requirement
Preserve empty-poll handling as a normal steady-state, not an error path.

---

## 5.2 Work polling must distinguish fatal from retryable failures
Fatal examples include:
- auth failure
- access denied
- environment/session expired/not found

Retryable examples include:
- connection loss
- transport-level IO failure
- server 5xx / transient bad-response class

### Rewrite requirement
Preserve the fatal-vs-retryable split for poll failures.

---

## 5.3 Sleep/wake detection resets connection error budgets
If the elapsed time since the last poll failure is far larger than normal backoff bounds, the runtime treats that as likely system sleep/wake and resets retry budgeting.

### Rewrite requirement
Preserve sleep-gap detection in long-running bridge poll loops.

---

## 5.4 At-capacity polling still needs to service existing-session redispatches
When already at capacity, the loop does not simply stop processing work forever. It still needs to handle token refresh / redispatch for already-running sessions.

### Rewrite requirement
Preserve “capacity blocks new spawns, not all work processing” semantics.

---

## 6. Work acknowledgment semantics

## 6.1 Work is acknowledged only after the bridge commits to handling it
The bridge intentionally does **not** acknowledge work too early.

Specifically, it avoids acknowledging before it has decided it can actually handle the work, because at-capacity or invalid-session cases may otherwise cause silent work loss.

### Rewrite requirement
Preserve late-enough acknowledgment semantics.

---

## 6.2 Acknowledge failure is non-fatal because work may be redelivered
If acknowledge fails, the bridge does not assume the session is irrecoverably broken.

### Rewrite requirement
Preserve dedup-safe behavior under ack uncertainty and redelivery.

---

## 6.3 Unknown or invalid work can still be acknowledged and skipped
Healthchecks and unknown/invalid work types are handled gracefully rather than poisoning the poll loop.

### Rewrite requirement
Preserve graceful acknowledgement-and-skip behavior for unsupported work variants.

---

## 7. Work secret semantics

## 7.1 A session work item carries a server-generated work secret that is authoritative
The work secret includes at least:
- session ingress token
- API base URL
- source/auth/environment metadata
- optional mode selectors such as `use_code_sessions`

### Rewrite requirement
Preserve work-secret decoding and validation as a strict step before session attach/spawn.

---

## 7.2 Work secret versioning is explicit
The secret includes a version, and unsupported versions must fail closed.

### Rewrite requirement
Preserve explicit work-secret version validation.

---

## 7.3 Session transport mode can be server-selected per work item
The work secret can select CCR v2/code-sessions behavior for a specific session.

### Rewrite requirement
Preserve per-session transport mode selection rather than a purely process-global mode.

---

## 8. Session spawn decision lifecycle

## 8.1 Existing-session redispatch is handled differently from new spawn
When work arrives for a session that is already running locally, the bridge does not spawn a second child. Instead it updates tokens/work bookkeeping for the existing child.

### Rewrite requirement
Preserve existing-session dedup/reattach semantics.

---

## 8.2 New sessions are only spawned if capacity permits
If the bridge is already at `maxSessions`, it must not spawn another child.

### Rewrite requirement
Preserve hard spawn-capacity enforcement.

---

## 8.3 Spawn mode is a lifecycle dimension, not just a UI option
The bridge supports distinct spawn modes with different cleanup/isolation behavior:
- `single-session`
- `worktree`
- `same-dir`

### Rewrite requirement
Preserve spawn mode as a real execution-policy choice, especially for session isolation and shutdown semantics.

---

## 8.4 Worktree mode gives later sessions isolated working trees
In worktree mode, on-demand concurrent sessions may get isolated git worktrees, while special first-session behavior can preserve legacy UX in the main directory.

### Rewrite requirement
Preserve per-session worktree isolation semantics when worktree mode is selected.

---

## 8.5 Spawn-time decisions must be snapshotted before async delay
The implementation snapshots mode/decision state before async work like worktree creation so later config mutation cannot retroactively change the accounting/analytics/behavior interpretation.

### Rewrite requirement
Preserve decision snapshots around async spawn boundaries.

---

## 9. Child process contract

## 9.1 Child sessions are launched in structured stream-json mode
The child CLI is launched with a structured stdin/stdout protocol rather than ad hoc human text.

### Rewrite requirement
Preserve a machine-readable child control/data protocol for bridge sessions.

---

## 9.2 Parent-to-child token updates happen over structured stdin, not only process env
When a session token refreshes, the parent sends an environment-variable update message to the already-running child over stdin.

### Rewrite requirement
Preserve live token refresh delivery into running child processes.

A rewrite must not require process restart for every session token refresh.

---

## 9.3 Child stdout is parsed as NDJSON and serves multiple roles simultaneously
The bridge parses child stdout to:
- track session activity summaries
- detect permission requests
- discover replayed user messages for title derivation
- archive/debug transcript lines

### Rewrite requirement
Preserve the multi-purpose role of structured child stdout.

---

## 9.4 Child stderr is diagnostic only, but retained in a ring buffer
Recent stderr lines are buffered for failure reporting/debugging.

### Rewrite requirement
Preserve a bounded stderr history for failed remote sessions.

---

## 10. Session activity model

The parent bridge derives user-facing session activity summaries from structured child output.

Typical activity classes include:
- tool start
- assistant text
- success result
- failure result

### Rewrite requirement
Preserve a separate session-activity model rather than scraping terminal text.

---

## 11. Title derivation and session naming

## 11.1 Server-supplied titles win over derived titles
If the server already has a session title, it should not be clobbered by locally derived first-message titles.

### Rewrite requirement
Preserve precedence of server-set titles over bridge-derived fallback titles.

---

## 11.2 Fallback title derivation comes from the first real user message
The bridge can derive a title from the first genuine user-authored message replayed by the child, skipping synthetic and tool-result wrapper messages.

### Rewrite requirement
Preserve filtering between real user prompts and synthetic/non-user replay events for title derivation.

---

## 12. Transport family split

A clean-room rewrite should preserve the fact that “remote transport” is actually a family of modes.

## 12.1 v1 bridge child transport
The bridge child process can use a mode with:
- WebSocket or similar streaming read path
- HTTP POST write path
- dynamic auth-header refresh on reconnect

## 12.2 CCR v2 child transport
The CCR v2 child process uses:
- SSE for reads
- HTTP POST for writes
- CCR worker registration/epoch
- internal event persistence/readback hooks
- state/metadata/delivery reporting

### Rewrite requirement
Preserve transport-mode-specific lifecycle rules instead of forcing one universal transport abstraction with identical semantics.

---

## 13. CCR v2 worker registration

## 13.1 CCR v2 requires worker registration before child session use
Before a v2 child can operate, the bridge registers itself as the worker and receives a `worker_epoch`.

### Rewrite requirement
Preserve explicit pre-child worker registration for CCR v2.

---

## 13.2 Worker epoch is required request context, not optional metadata
The epoch must be supplied back to the child so subsequent CCR requests are accepted in the correct worker incarnation.

### Rewrite requirement
Preserve worker-epoch threading through child process startup and transport calls.

---

## 13.3 Worker registration is retried briefly before giving up the session
Registration failure gets limited retry before the bridge abandons/stops the work item.

### Rewrite requirement
Preserve bounded retry around worker registration rather than infinite spin.

---

## 14. Session transport auth refresh

## 14.1 Session transport reconnect reads auth headers dynamically
Transport reconnect logic re-reads current auth headers instead of pinning only the original token forever.

### Rewrite requirement
Preserve dynamic header refresh for reconnecting transports.

---

## 14.2 Bridge parent and child maintain separate refresh responsibilities
The bridge parent may refresh/reissue session tokens, while the child transport must consume the new token during reconnect/write.

### Rewrite requirement
Preserve parent-issued token refresh plus child-side reconnect pickup.

---

## 14.3 v1 and v2 refresh strategies differ
- v1 can often update the running child’s active token directly
- v2 may require server-side redispatch/reconnect because worker endpoints validate session-specific claims

### Rewrite requirement
Preserve mode-specific token refresh behavior.

---

## 15. Heartbeat and lease semantics

## 15.1 Work lease heartbeat is separate from transport keepalive
Two different liveness mechanisms exist:
- **work heartbeat** to extend the server-side lease on a work item
- **transport keepalive/liveness** to maintain or detect health of the event stream

### Rewrite requirement
Preserve these as separate mechanisms.

---

## 15.2 Active work items are heartbeated explicitly
The bridge periodically heartbeats leased work items while sessions remain active.

### Rewrite requirement
Preserve explicit lease-heartbeat behavior for active work.

---

## 15.3 Auth failure during heartbeat triggers redispatch/reconnect logic
If a heartbeat fails because the session-ingress JWT expired, the bridge can request redispatch so fresh work with a fresh token arrives.

### Rewrite requirement
Preserve heartbeat-auth-failure recovery via server-side redispatch.

---

## 15.4 Fatal heartbeat failures are different from transient heartbeat failures
404/410-style environment expiry is terminal; generic failure is not necessarily terminal.

### Rewrite requirement
Preserve fatal-vs-retryable distinction on heartbeat failures.

---

## 16. Session-ingress keepalive semantics

In bridge child remote IO, the runtime emits synthetic keep_alive frames on a timer to keep otherwise idle sessions from being garbage-collected by intermediaries.

### Rewrite requirement
Preserve bridge-only keepalive emission for idle remote sessions where the network path requires it.

Important compatibility point:
- keepalive frames are infrastructure-level liveness signals
- they must be filtered before surfacing as normal user-visible session messages

---

## 17. Structured IO ordering and control semantics

## 17.1 Structured IO is a protocol layer, not just a serializer
The runtime tracks pending control requests, resolves control responses, rejects unresolved requests on input closure, and preserves outbound ordering.

### Rewrite requirement
Preserve StructuredIO-like request/response bookkeeping semantics.

---

## 17.2 Outbound ordering matters: control requests must not overtake queued stream events
The implementation uses a dedicated outbound queue/drain path so internally generated control traffic does not race ahead of prior events.

### Rewrite requirement
Preserve serialized outbound ordering across stream events and control_request messages.

---

## 17.3 Duplicate late control responses must be safely ignored
Resolved tool-use IDs are remembered in a bounded set so a duplicate/orphaned response does not re-insert duplicate assistant/tool state.

### Rewrite requirement
Preserve duplicate-control-response suppression for already-resolved tool uses.

---

## 18. Permission round-trip bridge invariant

## 18.1 Child permission requests are surfaced as structured control requests
When the child needs permission for a concrete tool invocation, it emits a control request that the bridge can forward to the server/UI.

### Rewrite requirement
Preserve structured per-invocation permission requests.

---

## 18.2 Permission responses are sent back as session events, not ad hoc side channels
The bridge responds by sending a `control_response` session event back through the session event API.

### Rewrite requirement
Preserve structured session-event permission responses.

---

## 18.3 Permission request lifecycle must remain correlated by request ID and tool-use ID
The identity of a permission decision is not just “latest prompt”; it is tied to concrete request and tool-use identifiers.

### Rewrite requirement
Preserve correlation keys for permission request/response routing.

---

## 19. Hybrid transport write invariants

## 19.1 Reads and writes are intentionally split
Hybrid transport uses one mechanism for reads and a different mechanism for writes.

### Rewrite requirement
Preserve split read/write transport semantics where used.

---

## 19.2 Writes are serialized to avoid concurrent server-side write collisions
The POST write path is serialized through an uploader queue rather than allowing arbitrary concurrent writes.

### Rewrite requirement
Preserve one-in-flight serialized write behavior for bridge transport POSTs.

---

## 19.3 Stream-event writes may be micro-batched briefly, but non-stream writes flush buffered stream events first
This reduces POST volume without violating ordering.

### Rewrite requirement
Preserve “buffer stream events briefly, but flush before non-stream event” ordering semantics.

---

## 19.4 Backpressure/memory bounds are explicit transport concerns
The serialized uploader has explicit batching, queue-size, retry, and dropped-batch considerations.

### Rewrite requirement
Preserve explicit write-queue policy rather than unconstrained buffering.

---

## 19.5 Close should attempt a best-effort drain before teardown
Transport close provides a grace period for queued writes to flush.

### Rewrite requirement
Preserve best-effort write drain on close.

---

## 20. SSE transport invariants

## 20.1 SSE reconnect resumes from the highest seen sequence number
SSE reconnect sends the last seen sequence cursor so the server can resume from the correct point.

### Rewrite requirement
Preserve sequence-based SSE resumption.

---

## 20.2 Duplicate SSE sequence numbers are tolerated and deduplicated heuristically
The runtime tracks seen sequence numbers in a bounded set to notice/tolerate replay or duplication near reconnect boundaries.

### Rewrite requirement
Preserve bounded duplicate-sequence handling around SSE reconnection.

---

## 20.3 Any SSE frame can reset liveness, including keepalive comments
Liveness detection is based on frame arrival, not only business payloads.

### Rewrite requirement
Preserve frame-level liveness reset semantics.

---

## 20.4 Liveness timeout forces reconnect even without explicit close
If the stream goes silent too long, the transport treats it as dead and reconnects.

### Rewrite requirement
Preserve liveness-timeout-based reconnect.

---

## 20.5 Some HTTP codes are permanent and should close rather than retry forever
401/403/404-class failures are treated as terminal for the SSE stream.

### Rewrite requirement
Preserve permanent server rejection handling for transport connect attempts.

---

## 20.6 Unexpected SSE event types are ignored but logged
Worker streams expect a constrained event type surface; unknown variants should not corrupt the local protocol.

### Rewrite requirement
Preserve tolerant-but-visible handling for unexpected SSE event variants.

---

## 21. RemoteIO invariants

## 21.1 Transport callbacks must be wired before connect begins
CCR-related callbacks and data handlers are set up before transport connection starts, so early frames are not lost.

### Rewrite requirement
Preserve callback wiring before opening the stream.

---

## 21.2 RemoteIO owns bridge-mode echo policy
In bridge mode, certain outbound messages such as control requests are echoed to stdout so the bridge parent can detect them; broader echoing is debug-dependent.

### Rewrite requirement
Preserve bridge-mode control-request echo behavior needed by the parent bridge.

---

## 21.3 Internal event persistence hooks are installed only in CCR v2 mode
CCR v2 registers internal event writers/readers so persistence and resume flow through the v2 event model.

### Rewrite requirement
Preserve mode-specific installation of transcript/internal-event hooks.

---

## 22. Reconnect and redispatch semantics

## 22.1 Reconnect of a session is not the same thing as reconnect of a transport socket
A bridge may ask the server to reconnect/redispatch a session when the worker/session token relationship changes, even if the transport implementation separately has its own socket reconnect logic.

### Rewrite requirement
Preserve distinct concepts of:
- transport reconnect
- session redispatch/reconnect
- environment re-registration

---

## 22.2 Existing-handle path is the key dedup barrier for redispatch
When redispatched work arrives for a session already active locally, the bridge updates the running handle instead of spawning again.

### Rewrite requirement
Preserve existing-handle dedup as a primary bridge invariant.

---

## 22.3 Resume-friendly shutdown differs from ordinary shutdown
In resumable single-session mode, the bridge may deliberately skip archival/deregistration so a continue command remains truthful.

### Rewrite requirement
Preserve shutdown-mode-specific archival/deregistration behavior for resumable sessions.

---

## 23. Shutdown and cleanup semantics

## 23.1 Shutdown first terminates children, then waits, then force-kills if necessary
A graceful SIGTERM window is attempted before SIGKILL.

### Rewrite requirement
Preserve staged child termination on bridge shutdown.

---

## 23.2 Cleanup must await in-flight stop/archive/worktree tasks before final process exit
The bridge tracks cleanup promises so teardown does not abandon critical server/workspace cleanup work mid-flight.

### Rewrite requirement
Preserve awaitable cleanup tracking for asynchronous shutdown tasks.

---

## 23.3 Session archiving and environment deregistration are separate steps
Archiving sessions removes them from active display semantics; deregistering the environment marks the bridge offline and cleans environment-side resources.

### Rewrite requirement
Preserve separate archive vs deregister semantics.

---

## 23.4 Worktree cleanup is tied to session lifecycle but must avoid double-removal races
Because session completion and shutdown can race, worktree cleanup logic snapshots/clears ownership before async deletion.

### Rewrite requirement
Preserve idempotent/race-safe worktree cleanup.

---

## 23.5 stopWork is best-effort but important
If a spawned or partially handled session cannot continue, the bridge best-effort informs the server via `stopWork`, with retry.

### Rewrite requirement
Preserve explicit stopWork cleanup on abandoned/failed work items.

---

## 24. Fatal conditions and user-visible truthfulness

## 24.1 Expired environment/session should surface as explicit expiry, not generic failure
Expiry is a first-class terminal condition.

### Rewrite requirement
Preserve explicit expired-session/environment messaging.

---

## 24.2 Cosmetic or suppressible permission-scope failures should not always surface as user-facing hard errors
Some 403s are operationally suppressible and should not poison the overall bridge state if core functionality still works.

### Rewrite requirement
Preserve suppressible-failure classification for selected bridge API errors.

---

## 24.3 Resume hints must only be printed when actually valid
The implementation avoids telling the user to resume if shutdown mode or fatal state made resume impossible.

### Rewrite requirement
Preserve truthful resume guidance conditioned on actual residual server state.

---

## 25. Suggested clean-room interfaces

A rewrite should expose interfaces roughly like:

```ts
interface BridgeEnvironmentManager {
  register(config: BridgeRegistration): Promise<RegisteredEnvironment>
  deregister(environmentId: string): Promise<void>
  pollWork(env: RegisteredEnvironment, signal?: AbortSignal): Promise<WorkItem | null>
  acknowledgeWork(envId: string, workId: string, sessionToken: string): Promise<void>
  heartbeatWork(envId: string, workId: string, sessionToken: string): Promise<LeaseHeartbeatResult>
  reconnectSession(envId: string, sessionId: string): Promise<void>
  archiveSession(sessionId: string): Promise<void>
  stopWork(envId: string, workId: string, force: boolean): Promise<void>
}

interface BridgeSessionSupervisor {
  spawn(spec: SpawnedSessionSpec): SessionHandle
  onSessionDone(sessionId: string, result: SessionDoneStatus): Promise<void>
  updateAccessToken(sessionId: string, token: string): void
}

interface SessionTransport {
  connect(): Promise<void>
  write(message: StdoutMessage): Promise<void>
  close(): void
  setOnData(cb: (data: string) => void): void
  setOnClose(cb: (code?: number) => void): void
}
```

For SSE resumption:

```ts
interface ResumableEventTransport extends SessionTransport {
  getResumeCursor(): number
}
```

---

## 26. Most critical invariants to preserve

## 26.1 Never spawn a second child for a session that is already active locally
Failure mode:
- duplicate local workers for one server session
- conflicting writes, duplicated tools, duplicate transcript effects

## 26.2 Work acknowledgment must happen only after the bridge is actually prepared to own that work
Failure mode:
- work item lost while bridge is at capacity or cannot spawn

## 26.3 Work lease heartbeat and transport keepalive must remain separate mechanisms
Failure mode:
- session appears alive locally while server lease expires, or vice versa

## 26.4 Transport reconnect must use fresh auth material when available
Failure mode:
- child transport enters permanent stale-token reconnect loop

## 26.5 SSE reconnect must resume from a transport cursor, not replay whole history blindly
Failure mode:
- duplicate event delivery and unbounded replay cost

## 26.6 Shutdown must distinguish resumable single-session shutdown from final archival teardown
Failure mode:
- printed resume commands lie, or resumable sessions are accidentally destroyed

## 26.7 Permission/control response routing must stay correlated by request/session identity
Failure mode:
- wrong permission decision applied to wrong tool invocation/session

## 26.8 Bridge state domains must stay separate: environment, work lease, child process, transport
Failure mode:
- impossible-to-debug recovery bugs and incorrect teardown/retry behavior

---

## 27. What matters most for rewrite compatibility

If a clean-room rewrite cannot reproduce every implementation detail, the highest-priority compatibility targets are:
1. environment/work/session/transport state separation
2. existing-session dedup on redispatch
3. late-enough ack semantics
4. correct token refresh and reconnect behavior
5. lease heartbeat correctness
6. truthful shutdown/archive/deregister behavior
7. ordered structured control/data transport handling
8. SSE/hybrid transport ordering and reconnect invariants

---

## 28. Confidence and limits

High confidence:
- environment registration/poll/ack/heartbeat/stop/archive/deregister semantics
- child spawn and token-refresh lifecycle
- hybrid and SSE transport ordering/reconnect behavior
- resumable vs final shutdown distinctions
- permission response routing model
- worktree/same-dir/single-session lifecycle differences

Moderate confidence:
- some of the single-process REPL bridge details are summarized here at the invariant level rather than exhaustively reconstructing every helper path

That is acceptable for a clean-room rewrite because the critical requirement is preserving the lifecycle and transport semantics visible to surrounding components, not reproducing every local logging or UI detail.
