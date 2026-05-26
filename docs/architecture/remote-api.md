# Remote API reference

This document extracts the verified remote HTTP API contracts used by the current codebase.

It is written for clean-room rewrite work. Every place that says a behavior must be preserved is spelled out here so the replacement behavior can be implemented from this document alone.

Primary source files:
- `src/utils/teleport/api.ts`
- `src/utils/teleport/environments.ts`
- `src/tools/RemoteTriggerTool/RemoteTriggerTool.ts`

This document is intentionally limited to endpoints, headers, request bodies, response shapes, client-side validation, and retry behavior that were directly observed in code.

---

## 1. Authentication and shared headers

> **Internal Anthropic API note**
> The Environments API, Remote Trigger API, `x-organization-uuid` header, and the OAuth/Bearer auth model described in this document should be treated as **internal Anthropic API**, not stable public API surface.
> The Sessions endpoints documented below may correspond to public beta surface, but the auth/header conventions observed in this codepath are still implementation-specific and should not be generalized as the public Claude API default.

## 1.1 OAuth requirement
Most remote APIs in this codepath require Claude.ai OAuth authentication.

### Required behavior
A compatible rewrite must require the following before calling the Sessions API, Environments API, or Remote Trigger API:
- an OAuth access token
- an organization UUID

### Observed token and org sources
- access token source: `getClaudeAIOAuthTokens()?.accessToken`
- organization UUID source: `getOrganizationUUID()`

### Contract implication
API key authentication alone is not sufficient for these APIs.

### Typical failure message
The existing code uses an auth/setup failure message equivalent to:

```text
Claude web sessions require authentication with a Claude.ai account. API key authentication is not sufficient. Please run /login to authenticate, or check your authentication status with /status.
```

A rewrite does not need the exact wording unless preserving user-visible strings is important, but it must preserve the auth requirement itself.

---

## 1.2 Shared OAuth header helper
**File:** `src/utils/teleport/api.ts`

### Helper contract
A helper equivalent to the following exists:

```ts
getOAuthHeaders(accessToken: string): Record<string, string>
```

### Required output
Given an access token, it must produce these base headers:

```http
Authorization: Bearer <accessToken>
Content-Type: application/json
anthropic-version: 2023-06-01
```

### Preservation requirement
Any compatible rewrite must send the same three base headers on all remote API calls documented here unless a later protocol migration intentionally changes them.

---

## 1.3 Additional organization and beta headers
Some endpoints require additional headers beyond the OAuth helper.

### Organization header
```http
x-organization-uuid: <orgUUID>
```

### Observed beta headers
```http
anthropic-beta: managed-agents-2026-04-01
```

### Preservation requirement
For Sessions and Environments references in this document, use `anthropic-beta: managed-agents-2026-04-01` where a beta header must be named.
Avoid pinning internal beta names for other endpoint families unless the endpoint is explicitly marked internal below.

---

## 1.4 Shared request preparation helper
**File:** `src/utils/teleport/api.ts`

### Helper contract
A helper equivalent to the following exists:

```ts
prepareApiRequest(): Promise<{
  accessToken: string
  orgUUID: string
}>
```

### Required behavior
Before making a remote request, this preparation step must:
1. verify an OAuth access token is available
2. verify an organization UUID is available
3. throw a clear setup/auth error before any HTTP request if either is missing

### Preservation requirement
A rewrite must fail early on missing auth/org prerequisites rather than attempting requests and relying on remote 401/400 responses.

---

## 2. Retry behavior

## 2.1 Transient error classification
**File:** `src/utils/teleport/api.ts`

### Helper contract
A helper equivalent to the following exists:

```ts
isTransientNetworkError(error: unknown): boolean
```

### Required classification rules
Return `true` only for:
- axios/network errors with **no HTTP response**
- HTTP 5xx responses

Return `false` for:
- non-axios/non-network errors
- HTTP 4xx responses

### Preservation requirement
A compatible rewrite must not retry 4xx application/client errors through the retry wrapper described below.

---

## 2.2 GET retry wrapper
**File:** `src/utils/teleport/api.ts`

### Helper contract
A helper equivalent to the following exists:

```ts
axiosGetWithRetry<T>(url: string, config?: AxiosRequestConfig): Promise<AxiosResponse<T>>
```

### Required retry policy
- total attempts: `5` including the initial attempt
- retry delays after failed attempts:
  - after attempt 1 failure: `2000 ms`
  - after attempt 2 failure: `4000 ms`
  - after attempt 3 failure: `8000 ms`
  - after attempt 4 failure: `16000 ms`
- retry only if `isTransientNetworkError(error) === true`
- do not retry 4xx responses

### Preservation requirement
This retry policy is part of the practical contract for session listing. A rewrite must preserve:
- same retry count
- same backoff sequence
- same retry eligibility rules

---

## 3. Sessions API

## 3.1 Session-related types
**File:** `src/utils/teleport/api.ts`

### `SessionStatus`
```ts
type SessionStatus = 'requires_action' | 'running' | 'idle' | 'archived'
```

### Session context source variants
```ts
type GitSource = {
  type: 'git_repository'
  url: string
  revision?: string | null
  allow_unrestricted_git_push?: boolean
}

type KnowledgeBaseSource = {
  type: 'knowledge_base'
  knowledge_base_id: string
}

type SessionContextSource = GitSource | KnowledgeBaseSource
```

### Outcome variants
```ts
type OutcomeGitInfo = {
  type: 'github'
  repo: string
  branches: string[]
}

type GitRepositoryOutcome = {
  type: 'git_repository'
  git_info: OutcomeGitInfo
}

type Outcome = GitRepositoryOutcome
```

### `SessionContext`
```ts
type SessionContext = {
  sources: SessionContextSource[]
  cwd: string
  outcomes: Outcome[] | null
  custom_system_prompt: string | null
  append_system_prompt: string | null
  model: string | null
  seed_bundle_file_id?: string
  github_pr?: { owner: string; repo: string; number: number }
  reuse_outcome_branches?: boolean
}
```

### `SessionResource`
```ts
type SessionResource = {
  type: 'session'
  id: string
  title: string | null
  session_status: SessionStatus
  environment_id: string
  created_at: string
  updated_at: string
  session_context: SessionContext
}
```

### `ListSessionsResponse`
```ts
type ListSessionsResponse = {
  data: SessionResource[]
  has_more: boolean
  first_id: string | null
  last_id: string | null
}
```

### Preservation requirement
A rewrite must preserve these consumed fields and enum values because downstream code depends on them for session display and repository inference.

---

## 3.2 `GET /v1/sessions`
**File:** `src/utils/teleport/api.ts`

### Purpose
Fetch the list of sessions.

### HTTP request
```http
GET {BASE_API_URL}/v1/sessions
```

### Required headers
```http
Authorization: Bearer <token>
Content-Type: application/json
anthropic-version: 2023-06-01
anthropic-beta: managed-agents-2026-04-01
x-organization-uuid: <orgUUID>
```

### Expected response status
```http
200 OK
```

### Response body shape
```ts
type ListSessionsResponse = {
  data: SessionResource[]
  has_more: boolean
  first_id: string | null
  last_id: string | null
}
```

### Client wrapper contract
The client wrapper is equivalent to:

```ts
fetchCodeSessionsFromSessionsAPI(): Promise<CodeSession[]>
```

### Required client behavior
1. Perform the request using the retry wrapper described earlier.
2. Require status `200`.
3. Transform `SessionResource[]` into `CodeSession[]`.

### Required transformation rules
For each `SessionResource`, produce a `CodeSession`-equivalent object with these derived values:
- `title = resource.title ?? 'Untitled'`
- `description = ''`
- `status = resource.session_status`
- `turns = []`
- `repo` derived from the first `git_repository` source if it can be parsed as a GitHub repository

### Repository derivation rules
If the first `git_repository` source can be parsed into GitHub `owner/name`, derive:

```ts
{
  name,
  owner: { login: owner },
  default_branch: gitSource.revision || undefined,
}
```

If the git source cannot be parsed as GitHub, omit the derived repo object.

### Preservation requirement
A compatible rewrite must preserve:
- the request URL and headers
- the use of retry behavior
- the exact transformation defaults above, especially `Untitled`, empty description, and empty turns

---

## 3.3 `GET /v1/sessions/{sessionId}`
**File:** `src/utils/teleport/api.ts`

### Purpose
Fetch one session by ID.

### HTTP request
```http
GET {BASE_API_URL}/v1/sessions/{sessionId}
```

### Required headers
```http
Authorization: Bearer <token>
Content-Type: application/json
anthropic-version: 2023-06-01
anthropic-beta: managed-agents-2026-04-01
x-organization-uuid: <orgUUID>
```

### Axios/request options
```ts
{
  timeout: 15000,
  validateStatus: status => status < 500,
}
```

### Success condition
```http
200 OK
```

### Required error mapping
If the response status is:
- `404`: throw an error equivalent to `Session not found: {sessionId}`
- `401`: throw an error equivalent to `Session expired. Please run /login to sign in again.`
- any other non-200 but `<500`: use `response.data.error.message` if present, otherwise throw a generic status-based error

### Preservation requirement
A compatible rewrite must preserve the timeout, `validateStatus` rule, and the special-case handling of `404` and `401`.

---

## 3.4 `POST /v1/sessions/{sessionId}/events`
**File:** `src/utils/teleport/api.ts`

### Purpose
Send a user-originated event into an existing remote session.

### HTTP request
```http
POST {BASE_API_URL}/v1/sessions/{sessionId}/events
```

### Required headers
```http
Authorization: Bearer <token>
Content-Type: application/json
anthropic-version: 2023-06-01
anthropic-beta: managed-agents-2026-04-01
x-organization-uuid: <orgUUID>
```

### Client wrapper contract
```ts
sendEventToRemoteSession(
  sessionId: string,
  messageContent: RemoteMessageContent,
  opts?: { uuid?: string },
): Promise<boolean>
```

### Input type
```ts
type RemoteMessageContent =
  | string
  | Array<{ type: string; [key: string]: unknown }>
```

### Request body shape
The request body must be:

```json
{
  "events": [
    {
      "uuid": "<event-uuid>",
      "session_id": "<sessionId>",
      "type": "user",
      "parent_tool_use_id": null,
      "message": {
        "role": "user",
        "content": "..."
      }
    }
  ]
}
```

### UUID rules
- if `opts.uuid` is provided, use it as the event UUID
- otherwise generate a fresh UUID
- this UUID passthrough behavior is required because the caller uses it for deduplication / echo filtering

### Axios/request options
```ts
{
  validateStatus: status => status < 500,
  timeout: 30000,
}
```

### Success and failure mapping
- `200` or `201` => return `true`
- any other status `<500` => return `false`
- thrown exception => return `false`

### Additional operational behavior
The client must tolerate the possibility that this endpoint blocks temporarily while the remote worker becomes ready.

### Preservation requirement
A compatible rewrite must preserve:
- exact request body envelope shape
- support for both string and structured-block content
- caller-provided UUID passthrough
- boolean success/failure mapping above

---

## 3.5 `PATCH /v1/sessions/{sessionId}`
**File:** `src/utils/teleport/api.ts`

### Purpose
Update a session title.

### HTTP request
```http
PATCH {BASE_API_URL}/v1/sessions/{sessionId}
```

### Required headers
```http
Authorization: Bearer <token>
Content-Type: application/json
anthropic-version: 2023-06-01
anthropic-beta: managed-agents-2026-04-01
x-organization-uuid: <orgUUID>
```

### Request body
```json
{ "title": "<new title>" }
```

### Client wrapper contract
```ts
updateSessionTitle(sessionId: string, title: string): Promise<boolean>
```

### Axios/request options
```ts
{
  validateStatus: status => status < 500,
}
```

### Success and failure mapping
- `200` => return `true`
- any other status `<500` => return `false`
- thrown exception => return `false`

### Preservation requirement
A compatible rewrite must preserve the exact request body shape and boolean success/failure mapping.

---

## 3.6 Session branch extraction helper
**File:** `src/utils/teleport/api.ts`

### Helper contract
```ts
getBranchFromSession(session: SessionResource): string | undefined
```

### Required behavior
- inspect `session.session_context.outcomes`
- find the first outcome with `type === 'git_repository'`
- return `git_info.branches[0]`
- if unavailable, return `undefined`

### Preservation requirement
This is not an HTTP endpoint, but it is part of the consumed session contract and should be preserved if downstream branch-aware UI/logic remains.

---

## 4. Environments API

> **Internal Anthropic API note**
> `/v1/environment_providers` and `/v1/environment_providers/cloud/create` should be treated as **internal Anthropic API**.
> Preserve them only for compatibility with this codepath; do not present them as stable public Claude API surface.

## 4.1 Environment-related types
**File:** `src/utils/teleport/environments.ts`

```ts
type EnvironmentKind = 'anthropic_cloud' | 'byoc' | 'bridge'
type EnvironmentState = 'active'

type EnvironmentResource = {
  kind: EnvironmentKind
  environment_id: string
  name: string
  created_at: string
  state: EnvironmentState
}

type EnvironmentListResponse = {
  environments: EnvironmentResource[]
  has_more: boolean
  first_id: string | null
  last_id: string | null
}
```

### Preservation requirement
These enum values and fields are part of the visible client contract and must remain stable unless coordinated across all consumers.

---

## 4.2 `GET /v1/environment_providers`
**File:** `src/utils/teleport/environments.ts`

### Purpose
List available environments.

### HTTP request
```http
GET {BASE_API_URL}/v1/environment_providers
```

### Required headers
```http
Authorization: Bearer <token>
Content-Type: application/json
anthropic-version: 2023-06-01
x-organization-uuid: <orgUUID>
```

### Client wrapper contract
```ts
fetchEnvironments(): Promise<EnvironmentResource[]>
```

### Axios/request options
```ts
{ timeout: 15000 }
```

### Success mapping
- require status `200`
- return `response.data.environments`

### Failure mapping
- non-200 response => throw an error equivalent to:

```text
Failed to fetch environments: <status> <statusText>
```

- thrown exception => log and rethrow an error equivalent to:

```text
Failed to fetch environments: <message>
```

### Preservation requirement
A compatible rewrite must preserve the exact endpoint, header set, 15s timeout, and the fact that the wrapper returns the inner `environments` array rather than the full envelope.

---

## 4.3 `POST /v1/environment_providers/cloud/create`
**File:** `src/utils/teleport/environments.ts`

### Purpose
Create a default cloud environment.

### HTTP request
```http
POST {BASE_API_URL}/v1/environment_providers/cloud/create
```

### Required headers
```http
Authorization: Bearer <token>
Content-Type: application/json
anthropic-version: 2023-06-01
anthropic-beta: ccr-byoc-2025-07-29
x-organization-uuid: <orgUUID>
```

### Client wrapper contract
```ts
createDefaultCloudEnvironment(name: string): Promise<EnvironmentResource>
```

### Required request body
```json
{
  "name": "<name>",
  "kind": "anthropic_cloud",
  "description": "",
  "config": {
    "environment_type": "anthropic",
    "cwd": "/home/user",
    "init_script": null,
    "environment": {},
    "languages": [
      { "name": "python", "version": "3.11" },
      { "name": "node", "version": "20" }
    ],
    "network_config": {
      "allowed_hosts": [],
      "allow_default_hosts": true
    }
  }
}
```

### Success mapping
- return `response.data` as `EnvironmentResource`

### Preservation requirement
A compatible rewrite must preserve the exact body defaults listed above unless the backend contract is intentionally migrated in tandem, including:
- `kind = anthropic_cloud`
- empty description
- `cwd = /home/user`
- Python `3.11`
- Node `20`
- default host allowance via `allow_default_hosts: true`

---

## 5. Remote trigger API

> **Internal Anthropic API note**
> `/v1/code/triggers`, `/v1/code/triggers/{trigger_id}`, and `/v1/code/triggers/{trigger_id}/run` should be treated as **internal Anthropic API**.
> Do not present this trigger surface as stable public Claude API. Avoid pinning internal beta names for it.

These endpoints are exposed through `RemoteTriggerTool` and are separate from the teleport session/environment helpers.

**File:** `src/tools/RemoteTriggerTool/RemoteTriggerTool.ts`

## 5.1 Shared remote-trigger behavior

### Feature and policy gates
The tool must only be enabled when both are true:
- feature flag `tengu_surreal_dali`
- policy `allow_remote_sessions`

### Auth behavior
Before dispatching the request:
1. refresh OAuth token if needed
2. acquire OAuth access token
3. acquire organization UUID

### Required headers
```http
Authorization: Bearer <token>
Content-Type: application/json
anthropic-version: 2023-06-01
anthropic-beta: ccr-triggers-2026-01-30
x-organization-uuid: <orgUUID>
```

### Base URL
```http
{BASE_API_URL}/v1/code/triggers
```

### Tool input schema
```ts
{
  action: 'list' | 'get' | 'create' | 'update' | 'run'
  trigger_id?: string
  body?: Record<string, unknown>
}
```

### Tool output schema
```ts
{
  status: number
  json: string
}
```

### Axios/request options
```ts
{
  timeout: 20000,
  validateStatus: () => true,
}
```

### Result mapping
For every action, the tool must return:

```ts
{
  status: <HTTP status code>,
  json: <JSON-stringified response body>
}
```

### Preservation requirement
A compatible rewrite must preserve the shared header set, base URL, timeout, permissive `validateStatus`, and raw status/body passthrough.

---

## 5.2 Action `list` -> `GET /v1/code/triggers`

### Tool input shape
```json
{ "action": "list" }
```

### Validation
- no additional fields required

### HTTP mapping
```http
GET {BASE_API_URL}/v1/code/triggers
```

### Read-only classification
- read-only: yes

### Preservation requirement
A rewrite must preserve this exact no-body list mapping.

---

## 5.3 Action `get` -> `GET /v1/code/triggers/{trigger_id}`

### Tool input shape
```json
{ "action": "get", "trigger_id": "abc" }
```

### Validation
- `trigger_id` is required
- client-side validation also requires `trigger_id` to match:

```regex
^[\w-]+$
```

### HTTP mapping
```http
GET {BASE_API_URL}/v1/code/triggers/{trigger_id}
```

### Read-only classification
- read-only: yes

### Preservation requirement
A compatible rewrite must preserve both the required field and the client-side identifier regex validation.

---

## 5.4 Action `create` -> `POST /v1/code/triggers`

### Tool input shape
```json
{
  "action": "create",
  "body": { "...": "..." }
}
```

### Validation
- `body` is required

### HTTP mapping
```http
POST {BASE_API_URL}/v1/code/triggers
```

### Request body
- send the provided `body` object as the JSON request body

### Read-only classification
- read-only: no

### Preservation requirement
A rewrite must preserve the fact that `create` sends caller-provided body content unchanged as the JSON payload.

---

## 5.5 Action `update` -> `POST /v1/code/triggers/{trigger_id}`

### Tool input shape
```json
{
  "action": "update",
  "trigger_id": "abc",
  "body": { "...": "..." }
}
```

### Validation
- `trigger_id` is required
- `body` is required

### HTTP mapping
```http
POST {BASE_API_URL}/v1/code/triggers/{trigger_id}
```

### Request body
- send the provided `body` object as the JSON request body

### Read-only classification
- read-only: no

### Preservation requirement
A compatible rewrite must preserve this exact action-to-method/path mapping even though the operation is named `update` and uses `POST` rather than `PATCH`.

---

## 5.6 Action `run` -> `POST /v1/code/triggers/{trigger_id}/run`

### Tool input shape
```json
{
  "action": "run",
  "trigger_id": "abc"
}
```

### Validation
- `trigger_id` is required

### HTTP mapping
```http
POST {BASE_API_URL}/v1/code/triggers/{trigger_id}/run
```

### Request body
```json
{}
```

### Read-only classification
- read-only: no

### Preservation requirement
A rewrite must preserve the explicit empty-object body for `run` requests.

---

## 5.7 Model-visible result mapping for `RemoteTriggerTool`

### Required rendered result
The tool must render its result as:

```text
HTTP <status>
<json>
```

where:
- `<status>` is the HTTP status code returned by the API
- `<json>` is the exact JSON-stringified response body returned in the structured `json` field

### Preservation requirement
This formatting must remain stable because callers/models may rely on it when interpreting trigger responses.

---

## 6. Endpoint preservation matrix

This section summarizes the exact mappings a clean-room rewrite must preserve.

| Surface | Method | Path | Required headers beyond OAuth base | Request body | Success contract |
|---|---|---|---|---|---|
| List sessions | GET | `/v1/sessions` | `anthropic-beta: managed-agents-2026-04-01`, `x-organization-uuid` | none | status `200`, transformed to `CodeSession[]` |
| Get session | GET | `/v1/sessions/{sessionId}` | `anthropic-beta: managed-agents-2026-04-01`, `x-organization-uuid` | none | status `200`, special-case `404` and `401` |
| Send session event | POST | `/v1/sessions/{sessionId}/events` | `anthropic-beta: managed-agents-2026-04-01`, `x-organization-uuid` | `{ events: [...] }` envelope | `200/201 => true`, else `false` |
| Update session title | PATCH | `/v1/sessions/{sessionId}` | `anthropic-beta: managed-agents-2026-04-01`, `x-organization-uuid` | `{ "title": ... }` | `200 => true`, else `false` |
| List environments | GET | `/v1/environment_providers` | `x-organization-uuid` | none | `200 => environments[]`, else throw |
| Create cloud environment | POST | `/v1/environment_providers/cloud/create` | `anthropic-beta: ccr-byoc-2025-07-29`, `x-organization-uuid` | fixed default environment payload | return `EnvironmentResource` |
| List triggers | GET | `/v1/code/triggers` | `anthropic-beta: ccr-triggers-2026-01-30`, `x-organization-uuid` | none | return `{ status, json }` |
| Get trigger | GET | `/v1/code/triggers/{trigger_id}` | `anthropic-beta: ccr-triggers-2026-01-30`, `x-organization-uuid` | none | return `{ status, json }` |
| Create trigger | POST | `/v1/code/triggers` | `anthropic-beta: ccr-triggers-2026-01-30`, `x-organization-uuid` | caller `body` | return `{ status, json }` |
| Update trigger | POST | `/v1/code/triggers/{trigger_id}` | `anthropic-beta: ccr-triggers-2026-01-30`, `x-organization-uuid` | caller `body` | return `{ status, json }` |
| Run trigger | POST | `/v1/code/triggers/{trigger_id}/run` | `anthropic-beta: ccr-triggers-2026-01-30`, `x-organization-uuid` | `{}` | return `{ status, json }` |

---

## 7. Clean-room rewrite checklist

A compatible rewrite must preserve all of the following from this document:

- OAuth token + organization UUID requirement
- shared OAuth header set
- endpoint-specific beta header mapping
- retry classification and backoff schedule
- all request paths and HTTP methods listed above
- the exact request envelope for remote session events
- UUID passthrough for remote session events
- exact default payload for cloud environment creation
- remote trigger action-to-endpoint mapping
- remote trigger raw status/body passthrough
- documented client-side status handling rules and boolean/throwing outcomes

---

## 8. Confidence level

High confidence:
- all endpoints, headers, request bodies, and client-side behaviors documented here were verified directly from code
- request/response shapes listed here were either explicitly typed or directly constructed in code

Lower confidence:
- server-side validation rules beyond the client validations listed here
- optional response fields not consumed by this client
