[← Back to index](README.md)

# 1. Concepts

## 1.1 Actors

- **Creator** (`bid_job_creator_id`) — whoever opens the bid job. Not
  otherwise validated or used by the service; it's stored as metadata on the
  job.
- **Subjects** (`bid_job_subject_ids`) — the roster of agents taking part in
  a job. In **closed** mode this is a fixed list decided at creation time,
  and it is required to bid. In **open** mode it starts empty and grows as
  subjects apply (see [§1.3](#13-bidding-modes)).
- **PQT function** (`bid_job_pqt_id`) — "pre-qualification test" function.
  Optional. If set, it is invoked synchronously for every incoming bid and
  can accept or reject it before it is persisted.
- **Evaluator function** (`bid_job_evaluator_id`) — required. Invoked exactly
  once per job, after every eligible subject has submitted a bid. It picks
  the winning subject.
- **Tie-breaker** (`bid_job_tie_id`) — reserved field, stored on the job and
  accepted by the API/schema, but **not currently invoked anywhere in
  `BiddingService`**. It exists for a future extension (e.g. calling a
  tie-break function when the evaluator can't produce a single winner).
  Today it is inert — treat it as forward-compatible schema, not active
  behavior.
- **Delegate system** (`SUBJECT_DELEGATE_URL`) — an external service that
  knows how to reach a live subject/agent and get a response back. Orcade
  never talks to a subject directly; it always goes through the delegate's
  `submit-and-wait` endpoint (see [§5](05-delegate-system.md)).
- **Function registry** (`FUNCTION_REGISTRY_URL`) — an external service that
  stores callable "functions" (PQT / evaluator implementations) and knows
  how to run them (stateless job, stateful deployment, or an external HTTP
  endpoint). Orcade resolves `bid_job_pqt_id` / `bid_job_evaluator_id`
  against this registry and invokes them (see [§4](04-functions.md)).

## 1.2 Lifecycle of a bid job

```
 1. POST /bid-jobs                         creator opens a job for a fixed
                                            list of subject_ids
         │
         ▼
 2. BiddingService.create_bid_job          job persisted in MongoDB;
         │                                 one background thread per
         │                                 subject fires a "bid_request"
         │                                 task to the delegate system
         ▼
 3. Each subject, asynchronously,
    submits its bid:
    POST /bid-jobs/{id}/bids
         │
         ▼
 4. BiddingService.submit_bid              - checks subject is eligible
         │                                 - (optional) calls the PQT
         │                                   function; rejects the bid on
         │                                   a negative verdict
         │                                 - persists the bid
         ▼
 5. After each bid, the service checks     once bids exist for ALL
    whether every eligible subject has     required subject_ids →
    now bid                                trigger evaluation
         │
         ▼
 6. BiddingService._evaluate (background   calls the evaluator function
    thread)                                with the job + all bids;
         │                                 reads back winner_subject_id,
         │                                 status, result_data
         ▼
 7. Winning bid flagged `is_winner=True`   a "bid_winner" task is sent to
    in MongoDB                             the winning subject via the
         │                                 delegate system
         ▼
 8. Every delegate round-trip (both        stored as a BidTaskResult,
    "bid_request" and "bid_winner")        queryable via
                                            /bid-jobs/{id}/task-results
```

Key behavioral notes:

- **Closed-mode evaluation is bid-driven, not time-driven.** There is no
  deadline/timer. The evaluator only runs once bids exist from *every*
  subject in `bid_job_subject_ids`. If even one eligible subject never bids,
  the job simply never evaluates. (Open mode closes on a limit instead; see
  §1.3.)
- **Notifications and evaluation are asynchronous.** `create_bid_job` and
  `submit_bid` return to the HTTP caller immediately; the delegate calls for
  `bid_request`/`bid_winner` and the evaluator call all run on background
  daemon threads. A client cannot assume a bid request or winner
  notification has already been delivered just because the HTTP call
  returned.
- **PQT rejection is synchronous and blocking.** Unlike notifications, the
  PQT function call happens inline inside `submit_bid` — the HTTP caller
  gets an immediate accept/reject.
- **The delegate's response is not interpreted by Orcade's logic.** Whatever
  JSON the delegate returns for a `bid_request` or `bid_winner` task is
  stored verbatim as a `BidTaskResult` for audit/history purposes; it does
  not feed back into who wins or whether a bid is accepted.

## 1.3 Bidding modes

Every job has a `bid_job_mode`: `closed` (the default), `open`, or `mixed`.

### Closed mode

The creator names the eligible subjects up front in `bid_job_subject_ids`.
Only those subjects may bid. Each is notified with a `bid_request` on
creation. Evaluation runs once every listed subject has bid. Lifecycle steps
1–8 in §1.2 describe this mode.

### Open mode

No subjects are named. Any subject may **apply**, and applying is submitting
a bid. The job closes when its limit is reached, and the set of applicants
at that moment is evaluated.

- **Limits.** Specify `bid_job_max_subjects` (maximum number of accepted
  applicants), `bid_job_max_time` (seconds from creation), or both. If both
  are set, the job closes on whichever is reached first. At least one is
  required.
- **Applying.** A subject submits `POST /bid-jobs/{id}/bids` as usual. The
  PQT function, if configured, runs first. If it accepts, the bid is stored
  and the subject is appended to `bid_job_subject_ids`. If it rejects, the
  subject is not added and nothing is stored.
- **Refusals.** An application is refused with `409` if the job is closed,
  past its deadline, already full, or the subject has already applied.
- **Closing.** Closing happens on whichever comes first:
  - the application that fills the last slot (`max_subjects`), or
  - a background watcher that notices `bid_job_closes_at` has passed (default
    poll interval 5 seconds, configurable via `BID_EXPIRY_INTERVAL_SECONDS`).

  Closing is atomic, so the evaluator runs at most once per job.
- **Empty close.** If the job closes with no applicants, it is marked closed
  and no evaluation runs.
- **No broadcast.** Open jobs send no `bid_request` notifications, since
  there is no fixed roster to notify. Subjects discover open jobs themselves,
  for example by querying `POST /bid-jobs/query` with
  `{"bid_job_mode": "open", "bid_job_status": "open"}`.

Open-mode request and response details are in [§3.2](03-apis.md#32-how-to-create-a-bid-job).

### Mixed mode

The creator names the eligible subjects up front, exactly like closed mode:
same required, non-empty `bid_job_subject_ids`, same `bid_request`
notification to each one on creation, same rule that evaluation runs once
every listed subject has bid. `bid_job_max_subjects` and `bid_job_max_time`
do not apply, since the roster is fixed at creation and nobody joins later.

The difference is tagging. For every subject in `bid_job_subject_ids`, the
job is automatically tagged `subject::<subject_id>` (see
[`SUBJECT_TAG_PREFIX`](02-schema.md#21-bidjob)), alongside whatever tags the
creator supplied. A subject can then find a job that names it with an
ordinary tag search or poll, via `GET /bid-jobs/by-tags` or
[`BidTagQuery`](06-using-client-library.md#63-dataclasses) — without
depending on the `bid_request` notification reaching it. This is the "mixed"
part: a fixed, closed roster (like closed mode) that is also discoverable by
tag (like open mode).

For example, creating a mixed-mode job with
`bid_job_subject_ids: ["agent-translator-01", "agent-translator-02"]` and
`bid_job_tags: ["translation"]` produces a stored `bid_job_tags` of
`["translation", "subject::agent-translator-01", "subject::agent-translator-02"]`.
If a subject tag duplicates one already in the creator's list, it is not
added twice ([§2.1](02-schema.md#21-bidjob) tag normalization still applies).

Bidding mechanics (eligibility, one bid per subject, PQT, evaluation) are
otherwise identical to closed mode. Mixed-mode request details are in
[§3.2](03-apis.md#32-how-to-create-a-bid-job).

---
[← Back to index](README.md) · [Next: Schema →](02-schema.md)
