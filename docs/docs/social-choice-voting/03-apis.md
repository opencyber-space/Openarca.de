[← Back to index](README.md)

# 3. APIs

The voting system exposes three HTTP servers and one WebSocket server. Routes
are mounted at the root. There is no auth or ACL layer, so treat every
endpoint as internal, trusted-network only.

| Server | Default address | Endpoints |
|---|---|---|
| Submission | `http://<host>:5000` | §3.2, §3.3 |
| Vote intake | `http://<host>:8081` | §3.4 (plus NATS, [§5.3](05-messaging.md#53-vote-submission-over-nats)) |
| Query | `http://<host>:8082` | §3.5 |
| Live stream | `ws://<host>:8765` | §3.6 |

## 3.1 Response format

There is no shared envelope. Success responses return the payload directly.
Failures return:

```json
{ "error": "human readable message" }
```

Each endpoint below lists its own success shape and status codes.

## 3.2 How to create a social task

`POST /submit-social-choice-task` (submission server)

Parses the request into the three entities in [§2](02-schema.md), generates a
`social_task_id`, and inserts the three documents. No invitations are sent at
this point. They go out when the scheduler starts the task
([§1.2](01-concepts.md#12-lifecycle-of-a-social-task)).

**Request body.** Three top-level objects. Every key listed is read with
`payload[...]`, so it must be present unless marked optional.

| Path | Maps to | Notes |
|---|---|---|
| `social_task.created_by_subject_id` | `created_by_subject_id` | |
| `social_task.created_by_subject_data` | `created_by_subject_data` | object |
| `social_task.org_ids` | `org_ids` | array of subject IDs |
| `social_task.access_type` | `social_task_access_type` | `"private"` or `"public"` |
| `social_task.goal` | `goal_data` | object |
| `social_task.topics` | `social_tasks_topics` | array |
| `social_task.properties` | `social_task_properties` | object |
| `social_task.creation_time` | `creation_time` | ISO-8601, no `Z` |
| `social_task.scheduled_time` | `scheduled_time` | optional. Naive ISO-8601 in UTC. Needed to start. |
| `social_task.duration` | `duration` | optional. Public vote threshold. |
| `social_task.status` | `status` | optional. Send `"scheduled"` for the task to start. |
| `social_task.report` | `report_json` | optional, default `{}` |
| `social_task.enable_live_streaming` | `enable_live_streaming` | optional, default `false` |
| `subject_spec.title` | `topic_title` | |
| `subject_spec.description` | `topic_description` | |
| `subject_spec.voting_options` | `voting_options_map` | object, option ID → label |
| `subject_spec.voting_metadata` | `voting_option_metadata_map` | object |
| `subject_spec.supported_protocols` | `supported_protocols` | array |
| `subject_spec.voting_request` | `voting_message_request_creator` | function spec, or `{}` |
| `evaluation_spec.constraints_primary` | `constraints_entry_id` | string, may be `""` |
| `evaluation_spec.constraints_secondary` | `constraints_entry_id_1` | string, may be `""` |
| `evaluation_spec.voting_pqt` | `voting_pqt` | function spec |
| `evaluation_spec.evaluation` | `choice_evaluation` | function spec |
| `evaluation_spec.tie_breaker` | `tie_breaker` | function spec, or `{}` |
| `evaluation_spec.post_award` | `post_awarding` | function spec |

Function specs are described in [§2.5](02-schema.md#25-function-spec).

**Private-task example.** Three named reviewers choose between three
translators. The task starts at 10:00 UTC.

```bash
curl -X POST http://localhost:5000/submit-social-choice-task \
  -H "Content-Type: application/json" \
  -d '{
    "social_task": {
      "created_by_subject_id": "planner-service",
      "created_by_subject_data": {"team": "localisation"},
      "org_ids": ["agent-reviewer-01", "agent-reviewer-02", "agent-reviewer-03"],
      "access_type": "private",
      "goal": {"objective": "Choose the lead translator for the Q4 handbook"},
      "topics": ["translation", "fr"],
      "properties": {"urgency": "high"},
      "creation_time": "2026-10-22T09:00:00",
      "scheduled_time": "2026-10-22T10:00:00",
      "status": "scheduled",
      "enable_live_streaming": true
    },
    "subject_spec": {
      "title": "Lead translator, Q4 handbook",
      "description": "Pick the agent that will lead the EN→FR translation of the Q4 handbook.",
      "voting_options": {
        "agent-translator-01": "Translator 01",
        "agent-translator-02": "Translator 02",
        "agent-translator-03": "Translator 03"
      },
      "voting_metadata": {},
      "supported_protocols": ["http"],
      "voting_request": {"mode": "function", "function_id": "voting-invite-builder:1.0-stable"}
    },
    "evaluation_spec": {
      "constraints_primary": "",
      "constraints_secondary": "",
      "voting_pqt": {"mode": "dsl", "workflow_id": "vote-option-is-valid:1.0"},
      "evaluation": {"mode": "dsl", "workflow_id": "plurality-count:1.0"},
      "tie_breaker": {"mode": "dsl", "workflow_id": "earliest-vote-wins:1.0"},
      "post_award": {"mode": "dsl", "workflow_id": "assign-lead-translator:1.0"}
    }
  }'
```

**Public-task example.** Changes from the private example: `access_type` is
`"public"`, `org_ids` is empty, and evaluation fires at 10 qualified votes.

```json
{
  "social_task": {
    "access_type": "public",
    "org_ids": [],
    "duration": 10,
    "...": "same as above"
  },
  "subject_spec": { "...": "same as above" },
  "evaluation_spec": { "...": "same as above" }
}
```

**Response `201 Created`:**

```json
{ "social_task_id": "task_3f9c6d2e" }
```

**Error responses:**

| Status | When |
|---|---|
| `400` | Empty or non-JSON body; one of `social_task`, `subject_spec`, `evaluation_spec` is missing; `creation_time` or `scheduled_time` is not a valid ISO-8601 string (a trailing `Z` is rejected) |
| `500` | A nested key is missing (`KeyError`), or the database insert fails. The body is always `{"error": "Internal server error"}`. Check the service log for the missing key. |

> Creation does not validate `access_type`, function specs, or whether
> `status` and `scheduled_time` are set. A task can be created successfully
> and still never start. See [§1.4](01-concepts.md#14-task-status).

## 3.3 How to validate a task without creating it

`POST /parse-social-choice-task` (submission server)

Runs the same parser as §3.2 and returns the result without writing anything.
Use it to check a payload and see the stored field names.

```bash
curl -X POST http://localhost:5000/parse-social-choice-task \
  -H "Content-Type: application/json" \
  -d @task.json
```

**Response `200`:**

```json
{
  "parsed": {
    "social_task": { "...": "SocialTaskCoreData.to_dict()" },
    "subject_spec": { "...": "SocialChoiceSubjectSpecInput.to_dict()" },
    "evaluation_spec": { "...": "SocialChoiceEvaluationInput.to_dict()" }
  }
}
```

The `social_task_id` in the response is freshly generated and is not
reserved. §3.2 generates a different ID. Errors are the same as §3.2.

## 3.4 How to submit a vote

`POST /submit-vote` (vote-intake server, port `8081`)

```bash
curl -X POST http://localhost:8081/submit-vote \
  -H "Content-Type: application/json" \
  -d '{
    "vote_id": "7d0f2a9c-2b4e-4a51-9a3e-0c6f1b2d4e8a",
    "social_task_id": "task_3f9c6d2e",
    "submitter_subject_id": "agent-reviewer-01",
    "vote_data": {"selected_option": "agent-translator-02"},
    "submission_time": "2026-10-22T10:03:12",
    "qualified": false
  }'
```

The body must contain **exactly** the six `Votes` fields, no more and no
fewer, because it is parsed with `Votes(**data)`. The server overwrites
`submission_time` and `qualified`, so any placeholder values work. The client
chooses `vote_id`.

Processing order inside `VoteAcceptor.accept_vote`:

1. Reject if `submitter_subject_id` already has a vote on this task, qualified
   or not.
2. Reject if the task does not exist.
3. Reject if the task status is not `"started"`.
4. **Private only:** reject if `submitter_subject_id` is not in `org_ids`.
5. Load the subject spec and evaluation spec. Reject if either is missing, or
   if no PQT is configured.
6. Run the PQT with the task, both specs, and `vote_data`
   ([§4.3](04-functions.md#43-pqt-pre-qualification-test)). `qualified` is
   `bool(result["qualified"])`.
7. Check whether evaluation should start, and if so, launch the Kubernetes
   Job ([§1.2](01-concepts.md#12-lifecycle-of-a-social-task) step 7).
8. If step 6 or step 7 raised, set `qualified = false`.
9. Persist the vote with the server's `submission_time` and the computed
   `qualified`.

**Response `200`:**

```json
{ "status": "accepted", "qualified": true }
```

`"status": "accepted"` means the vote was stored. A disqualified vote also
returns `200`, with `"qualified": false`, and still counts as this subject's
one vote.

**Error responses:**

| Status | When |
|---|---|
| `400` | Any failure: a missing or extra field, a rejection in steps 1 to 5, or a database error. The message is in `error`, for example `"Vote rejected: Vote already submitted for this task."` |

Rejection messages from steps 1 to 5:

| Message | Step |
|---|---|
| `Vote rejected: Vote already submitted for this task.` | 1 |
| `Vote rejected: Invalid social_task_id.` | 2 |
| `Vote rejected: Voting task is not active yet.` | 3 (also returned after the task is complete) |
| `Vote rejected: You are not authorized to vote in this private task.` | 4 |
| `Voting task configuration is incomplete.` | 5 |
| `Voting PQT DSL is not defined.` | 5 |

> The winner is **not** returned from this call. Poll `GET /get-status/<id>`
> until it returns `"complete"`, then read `GET /get-report/<id>` (§3.5). You
> can also subscribe to the winner's NATS subject ([§5.4](05-messaging.md#54-voting_result-sent-after-evaluation)).

## 3.5 Query endpoints

All on the query server (port `8082`).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/get-status/<social_task_id>` | Current task status |
| `GET` | `/get-report/<social_task_id>` | The final `report_json` |
| `GET` | `/get-full-task-bundle/<social_task_id>` | Task, specs, and all votes |
| `GET` | `/is-live-streaming-enabled/<social_task_id>` | Whether §3.6 will serve this task |
| `POST` | `/generic-query/<collection_name>` | Raw MongoDB filter on one collection |

Every endpoint returns `400 {"error": "..."}` on any failure, including an
unknown `social_task_id` (for example `"Error fetching status: Task not
found."`). None of them return `404`.

### `GET /get-status/<social_task_id>`

```bash
curl http://localhost:8082/get-status/task_3f9c6d2e
```
→ `200 { "status": "started" }`. The value is `null` if the task was created
without a status.

### `GET /get-report/<social_task_id>`

```bash
curl http://localhost:8082/get-report/task_3f9c6d2e
```
→ `200` with the `report_json` object itself, unwrapped
([§2.6](02-schema.md#26-report_json)). Before the task completes, this is
`{}`.

### `GET /get-full-task-bundle/<social_task_id>`

```bash
curl http://localhost:8082/get-full-task-bundle/task_3f9c6d2e
```
→ `200`:

```json
{
  "task": { "...": "SocialTaskCoreData.to_dict()" },
  "subject_spec": { "...": "SocialChoiceSubjectSpecInput.to_dict()" },
  "evaluation_input": { "...": "SocialChoiceEvaluationInput.to_dict()" },
  "votes": [ { "...": "Votes.to_dict()" } ]
}
```

`votes` includes disqualified votes. Filter on `qualified` yourself. Note the
key is `evaluation_input`, not `evaluation_spec` as in the report.

### `GET /is-live-streaming-enabled/<social_task_id>`

→ `200 { "enabled": true }`

### `POST /generic-query/<collection_name>`

The body is a **raw MongoDB filter document** passed to `collection.find()`.
`collection_name` must be one of `social_task_core_data`,
`social_choice_subject_spec`, `social_choice_evaluation_input`, or `votes`.
Any other name returns `400 {"error": "Error during query: Unsupported
collection: ..."}`.

```bash
# every task that is currently accepting votes
curl -X POST http://localhost:8082/generic-query/social_task_core_data \
  -H "Content-Type: application/json" \
  -d '{"status": "started"}'

# every vote a subject has cast
curl -X POST http://localhost:8082/generic-query/votes \
  -H "Content-Type: application/json" \
  -d '{"submitter_subject_id": "agent-reviewer-01"}'
```

> This endpoint returns documents with MongoDB's `_id`, which is not
> JSON-serializable. Today, any query that matches at least one document
> returns `400`, and only an empty result succeeds (`200 []`). See
> [§1.5 gap 7](01-concepts.md#15-current-implementation-gaps). Until that is
> fixed, use the per-task endpoints above.

## 3.6 WebSocket live stream

`ws://<host>:8765` (query system). The path is not checked.

The server pushes the full task bundle on a fixed interval, so dashboards can
watch votes arrive. It serves only tasks created with
`enable_live_streaming: true`.

**1. Connect and send one JSON message:**

```json
{ "social_task_id": "task_3f9c6d2e", "refresh_interval": 5 }
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `social_task_id` | string | required | |
| `refresh_interval` | int | `5` | Seconds between pushes |

**2. The server checks the task, then streams:**

```json
{
  "type": "update",
  "data": {
    "task": { "...": "..." },
    "subject_spec": { "...": "..." },
    "evaluation_input": { "...": "..." },
    "votes": [ "..." ]
  }
}
```

`data` is the same object as `GET /get-full-task-bundle` (§3.5). One message
is sent every `refresh_interval` seconds until the client disconnects. The
stream does not stop when the task completes. Watch `data.task.status` and
disconnect yourself.

**Errors.** The server sends one message and closes:

| Message | When |
|---|---|
| `{"error": "Missing social_task_id"}` | The field is absent |
| `{"error": "Invalid request format. Must be JSON with 'social_task_id' and 'refresh_interval'"}` | The first message is not JSON, or `refresh_interval` is not an integer |
| `{"error": "Live streaming not enabled for this task"}` | `enable_live_streaming` is `false` |

An unknown `social_task_id` closes the connection without an error message.
If a single push fails, for example on a database error, the failure is
logged and the next push is attempted on schedule.

**Example client:**

```python
import asyncio, json
import websockets

async def watch(task_id: str):
    async with websockets.connect("ws://localhost:8765") as ws:
        await ws.send(json.dumps({"social_task_id": task_id, "refresh_interval": 5}))
        async for raw in ws:
            msg = json.loads(raw)
            if "error" in msg:
                raise RuntimeError(msg["error"])
            task = msg["data"]["task"]
            votes = msg["data"]["votes"]
            print(task.get("status"), len(votes), "votes")
            if task.get("status") == "complete":
                break

asyncio.run(watch("task_3f9c6d2e"))
```

---
[← Previous: Schema](02-schema.md) · [Back to index](README.md) · [Next: Functions to write →](04-functions.md)
