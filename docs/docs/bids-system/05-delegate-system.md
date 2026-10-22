[← Back to index](README.md)

# 5. How input reaches a subject via the delegate system

Orcade never talks to a subject/agent directly. Every message to a subject
is routed through `SubjectTask` (`core/subject_task.py`), a thin client for
an external **delegate service** at `SUBJECT_DELEGATE_URL`.

## 5.1 Transport

```
POST {SUBJECT_DELEGATE_URL}/api/submit-and-wait
```

```json
{
  "subject_id": "agent-translator-01",
  "session_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10",
  "task_id": "3f9c6d2e-1a2b-4c3d-9e8f-7a6b5c4d3e2f",
  "task_data": { "...": "see 5.2 / 5.3" }
}
```

| Field | Value in Orcade's usage |
|---|---|
| `subject_id` | the target agent's ID (an entry from `bid_job_subject_ids`, or the resolved winner) |
| `session_id` | always the **`bid_job_id`** — every notification for a given job shares one delegate session |
| `task_id` | a fresh UUID4 per call, generated with `uuid4()` |
| `task_data` | the payload the subject actually needs to act — see below |

The call is a **blocking** `requests.post(...)` with a `(10, 300)`
second `(connect, read)` timeout — Orcade waits up to 5 minutes for the
delegate/subject to respond before the call fails. Whatever JSON the
delegate responds with is treated as the task's result and is not otherwise
parsed by Orcade's own logic (see [§5.4](#54-what-orcade-does-with-the-subjects-response)).

## 5.2 `bid_request` — sent on job creation

Fired once per subject in `bid_job_subject_ids`, each on its own daemon
thread, immediately inside `create_bid_job` (so it happens concurrently
across subjects, and does not block the `POST /bid-jobs` HTTP response).

**Closed mode only.** Open-mode jobs are created with an empty roster, so
no `bid_request` is sent. Applicants discover the job by querying for it.

```json
{
  "type": "bid_request",
  "bid_job": { "...": "full BidJob.to_dict()" },
  "bid_job_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10"
}
```

This is the entire payload a subject needs to decide whether/how to bid: the
full job object (including `bid_job_description`, the actual work spec) is
inlined — the subject does not need to call back into Orcade to fetch job
details.

## 5.3 `bid_winner` — sent after evaluation

Fired once, only to the subject whose `bid_subject_id` matches the
evaluator's `winner_subject_id`, after `is_winner` has been persisted on
the winning bid.

```json
{
  "type": "bid_winner",
  "bid_job_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10",
  "result_data": { "...": "the evaluator function's result_data verbatim" }
}
```

Note this payload is intentionally lean — it does **not** re-include the
full `bid_job` object (unlike `bid_request`); the winning subject is
expected to already have that context from having received the
`bid_request` and having submitted a bid itself. Everything the evaluator
wanted to communicate back (price agreed, start time, rationale, ...) must
be put into `result_data` by the evaluator function (see
[§4.3](04-functions.md#43-evaluator-function)).

## 5.4 What Orcade does with the subject's response

Both `bid_request` and `bid_winner` round-trips are recorded identically:
the delegate's raw JSON response becomes `BidTaskResult.task_result`,
tagged with the originating `task_type` (`"bid_request"` or
`"bid_winner"`), and inserted into the `bid_task_results` collection (see
[§2.3](02-schema.md#23-bidtaskresult)). Nothing in `BiddingService` reads
fields back out of these responses — there is no "subject declined the
bid_request" or "subject acknowledged winning" branch in the code today.
If you need that kind of feedback loop, build it on top of
`GET /bid-jobs/{id}/task-results` (poll/inspect `task_result` yourself, see
[§3.7](03-apis.md#37-bid-task-result-endpoints)) or extend `_notify_subject`
in `core/bidding.py`.

If the delegate call raises (timeout, non-2xx, connection error), the
error is logged and swallowed — **no `BidTaskResult` is written**, and (for
`bid_request`) the affected subject silently never gets notified, while
job creation itself still succeeds. There is currently no retry mechanism.

---
[← Previous: Functions to write](04-functions.md) · [Back to index](README.md)
