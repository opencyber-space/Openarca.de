[← Back to index](README.md)

# 2. Schema

All three entities are plain dataclasses (`core/schema.py`) that round-trip
through `to_dict()` / `from_dict()` and are stored as-is (no ORM/mapping
layer) as MongoDB documents.

## 2.1 `BidJob`

Represents a task that is open for bidding.

| Field | Type | Required | Description |
|---|---|---|---|
| `bid_job_id` | `string` (UUID4) | auto | Primary key. Generated server-side if omitted. |
| `bid_job_metadata` | `object` | yes (may be `{}`) | Free-form metadata about the job (e.g. deadlines, tags, source system). Not interpreted by Orcade; passed through to the PQT/evaluator functions and to subjects. |
| `bid_job_description` | `object` | yes (may be `{}`) | The actual task/work description a subject needs in order to construct a bid. Free-form — its shape is a contract between the creator and the subjects, not something Orcade validates. |
| `bid_job_name` | `object` | yes (may be `{}`) | Human-readable name/label for the job. Modeled as an object (not a plain string) so it can carry i18n variants or structured naming — e.g. `{"en": "..."}`. |
| `bid_job_evaluator_id` | `string` | **yes** | `function_id` in the function registry that will be invoked once all subjects have bid. See [§4.3](04-functions.md#43-evaluator-function). |
| `bid_job_pqt_id` | `string` | no (`""` = disabled) | `function_id` of the pre-qualification-test function invoked on every incoming bid. Empty string disables PQT checks entirely — bids are accepted unconditionally. See [§4.2](04-functions.md#42-pqt-pre-qualification-test-function). |
| `bid_job_tie_id` | `string` | stored, unused | Reserved for a future tie-breaker function. Accepted and persisted, never invoked today. |
| `bid_job_creator_id` | `string` | yes | Identifier of whoever created the job. Not validated against any user/subject registry. |
| `bid_job_subject_ids` | `array<string>` | closed: yes · open: no (`[]` at creation) | **Closed mode:** the fixed list of eligible, required subject IDs. Determines who gets a `bid_request` and when evaluation fires. **Open mode:** the roster of applicants, filled in by the service as PQT-passing subjects apply. Must not be supplied on creation of an open job. |
| `bid_job_mode` | `string` | no (default `"closed"`) | `"closed"` or `"open"`. Selects the bidding mode; see [§1.3](01-concepts.md#13-bidding-modes). |
| `bid_job_max_subjects` | `integer` ≥ 1 | open: at least one of this or `bid_job_max_time` · closed: must be omitted | Maximum number of accepted applicants. The job closes as soon as this many subjects have been accepted. |
| `bid_job_max_time` | `integer` ≥ 1 | open: at least one of this or `bid_job_max_subjects` · closed: must be omitted | Duration in **seconds**, measured from creation. The job closes once it passes. |
| `bid_job_status` | `string` | auto (`"open"`) | `"open"` or `"closed"`. Only meaningful in open mode. Flipped to `"closed"` atomically by whichever closing trigger fires first. |
| `bid_job_created_time` | `datetime` (ISO-8601 UTC string) | auto | When the job was created. Always stored in UTC with microsecond precision. |
| `bid_job_closes_at` | `datetime` (ISO-8601 UTC string) \| `null` | auto | `created_time + bid_job_max_time`, or `null` if no time limit is set. Open mode only. |
| `bid_job_tags` | `array<string>` | no (default `[]`) | Free-form labels for categorizing and finding the job, e.g. `["translation", "fr"]`. Used by `GET /bid-jobs/by-tags`. Each tag must be a non-empty string. Surrounding whitespace is stripped and duplicates are removed on creation. Matching is case-sensitive. |

**Example — full `BidJob` document (closed mode):**

```json
{
  "bid_job_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10",
  "bid_job_metadata": {
    "priority": "high",
    "deadline": "2026-09-15T00:00:00Z",
    "source_system": "task-planner"
  },
  "bid_job_description": {
    "task_type": "translate_document",
    "document_url": "https://storage.example.com/docs/report.pdf",
    "source_language": "en",
    "target_language": "fr",
    "word_count": 4200
  },
  "bid_job_name": {
    "en": "Translate Q3 report to French"
  },
  "bid_job_evaluator_id": "lowest-cost-evaluator:1.0-stable",
  "bid_job_pqt_id": "min-confidence-pqt:1.0-stable",
  "bid_job_tie_id": "",
  "bid_job_creator_id": "planner-service",
  "bid_job_subject_ids": [
    "agent-translator-01",
    "agent-translator-02",
    "agent-translator-03"
  ],
  "bid_job_mode": "closed",
  "bid_job_max_subjects": null,
  "bid_job_max_time": null,
  "bid_job_status": "open",
  "bid_job_created_time": "2026-09-09T10:00:00.000000+00:00",
  "bid_job_closes_at": null,
  "bid_job_tags": ["translation", "fr"]
}
```

**Example — full `BidJob` document (open mode, after two applicants):**

```json
{
  "bid_job_id": "c2d7f1a0-4e3b-4f19-9a52-7b8e1d6c0a33",
  "bid_job_metadata": {"source_system": "marketplace"},
  "bid_job_description": {
    "task_type": "translate_document",
    "source_language": "en",
    "target_language": "fr"
  },
  "bid_job_name": {"en": "Open call: translate Q4 handbook"},
  "bid_job_evaluator_id": "lowest-cost-evaluator:1.0-stable",
  "bid_job_pqt_id": "min-confidence-pqt:1.0-stable",
  "bid_job_tie_id": "",
  "bid_job_creator_id": "planner-service",
  "bid_job_subject_ids": ["agent-translator-07", "agent-translator-09"],
  "bid_job_mode": "open",
  "bid_job_max_subjects": 5,
  "bid_job_max_time": 3600,
  "bid_job_status": "open",
  "bid_job_created_time": "2026-10-05T09:00:00.000000+00:00",
  "bid_job_closes_at": "2026-10-05T10:00:00.000000+00:00",
  "bid_job_tags": ["translation", "marketplace"]
}
```

Here the roster has two entries out of a possible five. The job stays open
until either five subjects have applied or 10:00 UTC passes.

## 2.2 `Bid`

Represents one subject's bid for a job.

| Field | Type | Required | Description |
|---|---|---|---|
| `bid_id` | `string` (UUID4) | auto | Primary key. |
| `bid_job_id` | `string` | yes | FK to `BidJob.bid_job_id`. Set by the server from the URL path (`/bid-jobs/{bid_job_id}/bids`), not by the request body. |
| `bid_data` | `object` | yes (may be `{}`) | The actual content of the bid — free-form, defined by whatever the creator/evaluator expect (e.g. price, ETA, confidence score, proposed plan). This is what the PQT function and evaluator function reason over. |
| `bid_subject_id` | `string` | yes | Which subject this bid belongs to. In closed mode it must already be a member of the job's `bid_job_subject_ids`, or the bid is rejected (not persisted). In open mode there is no prior membership check. Instead, a successful application adds the subject to `bid_job_subject_ids`. In both modes, a subject may hold at most one bid per job. A second submission is refused with `409`. |
| `submission_time` | `datetime` (ISO-8601 string) | auto | Defaults to server time at construction. |
| `is_winner` | `boolean` | auto (`false`) | Flipped to `true` by the evaluation step for exactly one bid per job (the one matching `winner_subject_id`). Never set by the client. |

**Example — full `Bid` document:**

```json
{
  "bid_id": "3c7c3e2a-2d1a-4e2d-9a3b-6d2f9e6b0d4c",
  "bid_job_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10",
  "bid_data": {
    "price_usd": 120.0,
    "eta_hours": 6,
    "confidence": 0.92
  },
  "bid_subject_id": "agent-translator-01",
  "submission_time": "2026-09-09T10:15:32.481203",
  "is_winner": false
}
```

## 2.3 `BidTaskResult`

Audit record of every round-trip through the delegate system (i.e. every
`bid_request` and `bid_winner` notification and the subject's response to
it). See [§5](05-delegate-system.md).

| Field | Type | Required | Description |
|---|---|---|---|
| `bid_task_result_id` | `string` (UUID4) | auto | Primary key. |
| `bid_job_id` | `string` | yes | Which job this notification round-trip belongs to. |
| `bid_subject_id` | `string` | yes | Which subject was notified. |
| `task_type` | `string` | yes | Either `"bid_request"` or `"bid_winner"` (see §5). |
| `task_result` | `object` | yes | The raw JSON body returned by the delegate system's `/api/submit-and-wait` call. Opaque to Orcade — stored verbatim. |
| `created_time` | `datetime` (ISO-8601 string) | auto | When the result was recorded. |

**Example — full `BidTaskResult` document:**

```json
{
  "bid_task_result_id": "a1b2c3d4-5678-4abc-9def-0123456789ab",
  "bid_job_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10",
  "bid_subject_id": "agent-translator-01",
  "task_type": "bid_request",
  "task_result": {
    "acknowledged": true,
    "agent_notes": "Received job, computing bid now."
  },
  "created_time": "2026-09-09T10:15:01.001000"
}
```

## 2.4 Storage

All three entities live in MongoDB, database `assets` (`MONGO_URL`, default
`mongodb://localhost:27017`), one collection each:

| Collection | Unique index | Secondary indexes |
|---|---|---|
| `bid_jobs` | `bid_job_id` | `bid_job_evaluator_id`, `bid_job_creator_id`, compound `(bid_job_mode, bid_job_status, bid_job_closes_at)` used by the expiry watcher |
| `bids` | `bid_id` | `bid_job_id`, `bid_subject_id`, `is_winner` |
| `bid_task_results` | `bid_task_result_id` | `bid_job_id`, `bid_subject_id` |

`update()` and `delete()` on any of the databases operate by the entity's own
UUID field (`bid_job_id` / `bid_id`), never by Mongo's internal `_id`. Every
`query()` call accepts a **raw MongoDB filter document** — see
[§3.6](03-apis.md#36-query-endpoints).

---
[← Previous: Concepts](01-concepts.md) · [Back to index](README.md) · [Next: APIs →](03-apis.md)
