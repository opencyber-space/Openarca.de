[← Back to index](README.md)

# 3. APIs

Base path: none (routes are mounted at root). Default port `5000`
(`run_server()` in `core/apis.py`; overridable via the `PORT` env var at the
WSGI/container level — Flask's dev server itself is hardcoded to `0.0.0.0:5000`
in `run_server()`).

## 3.1 Response envelope

Every endpoint replies with the same envelope:

```json
// success
{ "ok": true, "data": { ... } }

// failure
{ "ok": false, "error": "human readable message" }
```

`data` may be a single object, a list, or omitted entirely (e.g. update
responses only return `{"modified": <count>}`).

## 3.2 How to create a bid job

`POST /bid-jobs`

Creates the job, persists it, and (asynchronously, one thread per subject)
sends a `bid_request` task to every ID in `bid_job_subject_ids` via the
delegate system.

**Request body:**

| Field | Type | Default if omitted |
|---|---|---|
| `bid_job_metadata` | object | `{}` |
| `bid_job_description` | object | `{}` |
| `bid_job_name` | object | `{}` |
| `bid_job_evaluator_id` | string | `""` (job will never evaluate) |
| `bid_job_pqt_id` | string | `""` (no pre-qualification) |
| `bid_job_tie_id` | string | `""` |
| `bid_job_creator_id` | string | `""` |
| `bid_job_subject_ids` | array<string> | `[]` |
| `bid_job_mode` | string | `"closed"` (`"open"` for open-mode) |
| `bid_job_max_subjects` | integer ≥ 1 | `null` |
| `bid_job_max_time` | integer ≥ 1 (seconds) | `null` |
| `bid_job_tags` | array<string> | `[]` |

**Validation (`400` on failure):**

| Mode | Rule |
|---|---|
| any | `bid_job_mode` must be `"closed"` or `"open"` |
| `open` | `bid_job_subject_ids` must be empty or omitted |
| `open` | at least one of `bid_job_max_subjects` / `bid_job_max_time` must be set |
| `open` | any limit that is set must be a positive integer (booleans are rejected) |
| `closed` | `bid_job_max_subjects` and `bid_job_max_time` must be omitted |
| any | `bid_job_tags` must be a list of non-empty strings (`400` otherwise) |

**Open-mode example** — no subjects named; closes after five applicants or one hour, whichever comes first:

```bash
curl -X POST http://localhost:5000/bid-jobs \
  -H "Content-Type: application/json" \
  -d '{
    "bid_job_name": {"en": "Open call: translate Q4 handbook"},
    "bid_job_description": {"task_type": "translate_document", "target_language": "fr"},
    "bid_job_evaluator_id": "lowest-cost-evaluator:1.0-stable",
    "bid_job_pqt_id": "min-confidence-pqt:1.0-stable",
    "bid_job_creator_id": "planner-service",
    "bid_job_mode": "open",
    "bid_job_max_subjects": 5,
    "bid_job_max_time": 3600
  }'
```

Response `201` returns the job with `bid_job_subject_ids: []`,
`bid_job_status: "open"`, and `bid_job_closes_at` set to creation time plus
3600 seconds.

**Closed-mode example** — fixed roster of two subjects:

```bash
curl -X POST http://localhost:5000/bid-jobs \
  -H "Content-Type: application/json" \
  -d '{
    "bid_job_name": {"en": "Translate Q3 report to French"},
    "bid_job_description": {
      "task_type": "translate_document",
      "document_url": "https://storage.example.com/docs/report.pdf",
      "source_language": "en",
      "target_language": "fr"
    },
    "bid_job_metadata": {"priority": "high"},
    "bid_job_evaluator_id": "lowest-cost-evaluator:1.0-stable",
    "bid_job_pqt_id": "min-confidence-pqt:1.0-stable",
    "bid_job_creator_id": "planner-service",
    "bid_job_subject_ids": ["agent-translator-01", "agent-translator-02"]
  }'
```

**Response `201 Created`:**

```json
{
  "ok": true,
  "data": {
    "bid_job_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10",
    "bid_job_metadata": {"priority": "high"},
    "bid_job_description": { "...": "..." },
    "bid_job_name": {"en": "Translate Q3 report to French"},
    "bid_job_evaluator_id": "lowest-cost-evaluator:1.0-stable",
    "bid_job_pqt_id": "min-confidence-pqt:1.0-stable",
    "bid_job_tie_id": "",
    "bid_job_creator_id": "planner-service",
    "bid_job_subject_ids": ["agent-translator-01", "agent-translator-02"]
  }
}
```

Failure modes: `400` if the DB insert fails (`RuntimeError`), `500` on any
other unexpected error.

## 3.3 How to submit a bid

`POST /bid-jobs/{bid_job_id}/bids`

```bash
curl -X POST http://localhost:5000/bid-jobs/8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10/bids \
  -H "Content-Type: application/json" \
  -d '{
    "bid_subject_id": "agent-translator-01",
    "bid_data": {"price_usd": 120.0, "eta_hours": 6, "confidence": 0.92}
  }'
```

Processing order inside `BiddingService.submit_bid` (closed mode):

1. Look up the job. `404` if missing (`ValueError` containing `"not found"`).
2. Check `bid_subject_id` is in `bid_job.bid_job_subject_ids`. `400` if not.
3. Check the subject has no existing bid on this job. `409` if it does, so a
   subject holds at most one bid per job.
4. If `bid_job_pqt_id` is set, synchronously call the PQT function with
   `{"bid_job": <job>, "bid": <bid>}`. If the response's `"accepted"` key is
   falsy, the bid is **rejected and never persisted** → `409`.
5. Persist the bid. `500` if the DB insert fails.
6. Check whether every subject in `bid_job_subject_ids` now has a bid on
   file; if so, kick off evaluation on a background thread.

**Open mode** (`bid_job_mode: "open"`) — the same endpoint is an *application*:

1. Look up the job. `404` if missing.
2. Refuse with `409` if the job is not open, its `bid_job_closes_at` has
   passed, or the subject is already in `bid_job_subject_ids`. `bid_subject_id`
   is not checked against a roster, since there isn't one.
3. Run the PQT function as above. A rejection → `409`, nothing stored.
4. Persist the bid.
5. **Atomically claim a slot.** In one database write, add the subject to
   `bid_job_subject_ids` only if the job is still open, not past its deadline,
   not already containing the subject, and below `bid_job_max_subjects`. If
   that write matches nothing, the job filled or closed in the meantime. The
   bid from step 4 is deleted and the request gets `409`.
6. If the claim filled the last slot, close the job and evaluate it on a
   background thread.

The bid is stored before the subject joins the roster, so every subject in
`bid_job_subject_ids` already has a bid on file when evaluation runs.

Open-mode request example:

```bash
curl -X POST http://localhost:5000/bid-jobs/c2d7f1a0-4e3b-4f19-9a52-7b8e1d6c0a33/bids \
  -H "Content-Type: application/json" \
  -d '{
    "bid_subject_id": "agent-translator-11",
    "bid_data": {"price_usd": 110.0, "eta_hours": 8, "confidence": 0.88}
  }'
```

Success returns `201` with the bid, as below. Subject `agent-translator-11`
is now in the job's roster. Refusal returns:

```json
{ "ok": false, "error": "Subject 'agent-translator-11' has already applied to job 'c2d7f1a0-4e3b-4f19-9a52-7b8e1d6c0a33'." }
```

with `409`. Other refusal messages are `"Bid job '…' is closed."`,
`"Bid job '…' has passed its deadline."`, and `"Bid job '…' is full or closed."`.

**Response `201 Created`:**

```json
{
  "ok": true,
  "data": {
    "bid_id": "3c7c3e2a-2d1a-4e2d-9a3b-6d2f9e6b0d4c",
    "bid_job_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10",
    "bid_data": {"price_usd": 120.0, "eta_hours": 6, "confidence": 0.92},
    "bid_subject_id": "agent-translator-01",
    "submission_time": "2026-09-09T10:15:32.481203",
    "is_winner": false
  }
}
```

**Error responses:**

| Status | When |
|---|---|
| `400` | `bid_subject_id` missing from request body, or (closed mode) subject not in the roster |
| `404` | `bid_job_id` does not exist |
| `409` | The subject already bid on this job, PQT function rejected the bid (`{"accepted": false, ...}`), or (open mode) the job is closed, past its deadline, or full |
| `500` | DB failure, or unexpected exception |

```json
// 409 example
{ "ok": false, "error": "Bid 'ca11...' rejected by pqt function 'min-confidence-pqt:1.0-stable'." }
```

> Winner selection is **not** returned synchronously from this call. Poll
> `GET /bid-jobs/{id}/bids` (look for `"is_winner": true`) or
> `GET /bid-jobs/{id}/task-results` (look for a `"bid_winner"` entry), or
> have the winning subject watch for the `bid_winner` delegate task itself.

## 3.4 Bid Job endpoints — full reference

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/bid-jobs` | Create a bid job (§3.2) |
| `GET` | `/bid-jobs/by-tags` | Find jobs by tag (§3.4.1) |
| `GET` | `/bid-jobs/{bid_job_id}` | Fetch one job by ID |
| `PUT` / `PATCH` | `/bid-jobs/{bid_job_id}` | Partially update a job (raw `$set`) |
| `DELETE` | `/bid-jobs/{bid_job_id}` | Delete a job |
| `POST` | `/bid-jobs/query` | Query jobs with a raw Mongo filter |

`GET /bid-jobs/{bid_job_id}`

```bash
curl http://localhost:5000/bid-jobs/8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10
```
→ `200 { "ok": true, "data": <BidJob> }`, or `404 { "ok": false, "error": "No document found" }`.

### 3.4.1 Find bid jobs by tags

`GET /bid-jobs/by-tags`

Returns every bid job whose `bid_job_tags` match the requested tags.

**Query parameters:**

| Parameter | Required | Description |
|---|---|---|
| `tags` | yes | Tags to search for. Give comma-separated values (`tags=translation,fr`), a repeated parameter (`tags=translation&tags=fr`), or both. Each tag is trimmed, and empty tags are rejected. |
| `match` | no (default `all`) | `all`: a job matches only if it carries **every** requested tag, so the requested tags must be a subset of the job's tags. `any`: a job matches if it carries **at least one** requested tag. |

Matching is case-sensitive and uses the same normalization as creation.
Results are not filtered by mode or status, so open and closed jobs, and
jobs in any status, can all match. Add a status check on the client if you
only want open jobs.

```bash
# jobs tagged with both "translation" and "fr"
curl "http://localhost:5000/bid-jobs/by-tags?tags=translation,fr"

# jobs tagged with "legal" or "finance"
curl "http://localhost:5000/bid-jobs/by-tags?tags=legal,finance&match=any"
```

Response `200`:

```json
{
  "ok": true,
  "data": [
    {
      "bid_job_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10",
      "bid_job_name": {"en": "Translate Q3 report to French"},
      "bid_job_tags": ["translation", "fr"],
      "bid_job_mode": "closed",
      "...": "remaining BidJob fields"
    }
  ]
}
```

No matches returns `200` with `"data": []`.

| Status | When |
|---|---|
| `400` | `tags` is missing or blank, a tag is empty, or `match` is not `all` or `any` |
| `500` | Unexpected database error |

`PUT` / `PATCH /bid-jobs/{bid_job_id}`

Body is applied as a MongoDB `$set` on arbitrary top-level fields — there is
no schema validation on update. Typical use: closing off further bids by
clearing `bid_job_subject_ids`, or patching `bid_job_metadata`.

```bash
curl -X PATCH http://localhost:5000/bid-jobs/8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10 \
  -H "Content-Type: application/json" \
  -d '{"bid_job_metadata": {"priority": "low"}}'
```
→ `200 { "ok": true, "data": {"modified": 1} }`, or `404` if nothing matched
(id not found, or the new values equal the old ones — `modified_count`
reflects Mongo's actual write, not existence).

`DELETE /bid-jobs/{bid_job_id}`
```bash
curl -X DELETE http://localhost:5000/bid-jobs/8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10
```
→ `200 { "ok": true, "data": {"deleted": 1} }`, or `404` if not found.

## 3.5 Bid endpoints — full reference

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/bid-jobs/{bid_job_id}/bids` | Submit a bid (§3.3) |
| `GET` | `/bid-jobs/{bid_job_id}/bids` | List all bids for a job |
| `GET` | `/bids/{bid_id}` | Fetch one bid |
| `PUT` / `PATCH` | `/bids/{bid_id}` | Raw `$set` update on a bid |
| `DELETE` | `/bids/{bid_id}` | Delete a bid |
| `POST` | `/bids/query` | Query bids with a raw Mongo filter |

```bash
curl http://localhost:5000/bid-jobs/8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10/bids
```
→
```json
{ "ok": true, "data": [ { "bid_id": "...", "is_winner": true, "...": "..." } ] }
```

> There is no dedicated "get winner" endpoint — filter the bids list (or
> use `/bids/query` with `{"bid_job_id": "...", "is_winner": true}`) client-side.

## 3.6 Query endpoints

`POST /bid-jobs/query`, `POST /bids/query`, and `POST /bid-task-results/query`
(note: task results only expose `query`, not full CRUD) all take a **raw
MongoDB filter document** as the request body and return a list of matching
documents in the same shape as `to_dict()`.

```bash
# all bids submitted by a given subject, across all jobs
curl -X POST http://localhost:5000/bids/query \
  -H "Content-Type: application/json" \
  -d '{"bid_subject_id": "agent-translator-01"}'

# the winning bid for a job
curl -X POST http://localhost:5000/bids/query \
  -H "Content-Type: application/json" \
  -d '{"bid_job_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10", "is_winner": true}'

# every job a given evaluator function is attached to
curl -X POST http://localhost:5000/bid-jobs/query \
  -H "Content-Type: application/json" \
  -d '{"bid_job_evaluator_id": "lowest-cost-evaluator:1.0-stable"}'
```

Because the filter is passed straight to `collection.find()`, any valid
Mongo query operator works (`$gt`, `$in`, `$exists`, ...). There is no
projection support and no auth/ACL layer — treat these endpoints as
internal/trusted-network only.

## 3.7 Bid Task Result endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/bid-jobs/{bid_job_id}/task-results` | All delegate round-trips for a job |
| `POST` | `/bid-task-results/query` | Raw Mongo filter query |

```bash
curl http://localhost:5000/bid-jobs/8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10/task-results
```
```json
{
  "ok": true,
  "data": [
    {
      "bid_task_result_id": "...",
      "bid_job_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10",
      "bid_subject_id": "agent-translator-01",
      "task_type": "bid_request",
      "task_result": {"acknowledged": true},
      "created_time": "2026-09-09T10:15:01.001000"
    },
    {
      "bid_task_result_id": "...",
      "bid_job_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10",
      "bid_subject_id": "agent-translator-02",
      "task_type": "bid_winner",
      "task_result": {"acknowledged": true, "will_start": "2026-09-10T09:00:00Z"},
      "created_time": "2026-09-09T10:16:45.221000"
    }
  ]
}
```

---
[← Previous: Schema](02-schema.md) · [Back to index](README.md) · [Next: Functions to write →](04-functions.md)
