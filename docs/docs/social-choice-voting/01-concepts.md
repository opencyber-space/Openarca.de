[← Back to index](README.md)

# 1. Concepts

## 1.1 Actors

- **Creator** (`created_by_subject_id`): whoever submits the social task.
  Stored as metadata. It is also used as `sender_subject_id` on invitations
  ([§5.2](05-messaging.md#52-voting_invite-sent-when-a-task-starts)). It is not
  checked against any subject registry.
- **Voters**: subjects that submit votes. In **private** tasks only the
  subjects listed in `org_ids` may vote. In **public** tasks any subject may
  vote. See [§1.3](#13-access-modes).
- **Voting options** (`voting_options_map`): the choices being voted on,
  keyed by option ID. The system also uses each option key as an address:
  invitations go to one channel per option key, and result notifications go
  to each winner ID. In practice, then, option keys are subject IDs, that is,
  the candidates. See [§5](05-messaging.md).
- **Invitation creator** (`voting_message_request_creator`): optional. A
  function or DSL workflow that builds custom content for the invitation
  message when the task starts. See [§4.2](04-functions.md#42-invitation-creator).
- **PQT** (`voting_pqt`): the pre-qualification test. It runs once for every
  incoming vote and decides whether the vote is `qualified`. A disqualified
  vote is still stored, but evaluation ignores it. See [§4.3](04-functions.md#43-pqt-pre-qualification-test).
- **Choice evaluation** (`choice_evaluation`): required. It runs once per task,
  inside the evaluator job, over all qualified votes, and returns one winner
  or several. See [§4.4](04-functions.md#44-choice-evaluation).
- **Tie-breaker** (`tie_breaker`): optional. It runs only when choice
  evaluation returns more than one winner. Unlike the bidding system's
  `bid_job_tie_id`, this hook is active. See [§4.5](04-functions.md#45-tie-breaker).
- **Post-award** (`post_awarding`): required. It runs after the winners are
  final. Its output is stored in the report and sent with the result
  notification. See [§4.6](04-functions.md#46-post-award).
- **Constraints** (`constraints_entry_id`, `constraints_entry_id_1`) and
  **supported protocols** (`supported_protocols`): stored on the task but not
  read by any service today. Treat them as forward-compatible schema.
- **Function registry** (`FUNCTIONS_REGISTRY_URL`) and **DSL workflow
  registry** (`DSL_WORKFLOW_URL`, `WORKFLOWS_API_URL`): external services
  that host the hook logic. See [§4.1](04-functions.md#41-two-ways-to-plug-in-logic).
- **Messaging**: Redis pub/sub (`ORG_REDIS_URL`) carries invitations. NATS
  (`ORG_NATS_URL`) carries incoming votes and result notifications. See
  [§5](05-messaging.md).
- **Kubernetes**: each evaluation runs as a one-off Job in the
  `votes-evaluation` namespace.

## 1.2 Lifecycle of a social task

```
 1. POST /submit-social-choice-task        creator submits task, subject
         │                                  spec, and evaluation spec
         ▼
 2. SocialTaskController                   three documents persisted in
         │                                 MongoDB under one generated
         │                                 social_task_id; status is
         │                                 whatever the request supplied
         ▼
 3. CronScheduler (every 60 s)             finds tasks with
         │                                 status == "scheduled" and
         │                                 scheduled_time <= now (UTC)
         ▼
 4. VotingTaskInitiator                    - (optional) runs the
         │                                   invitation creator
         │                                 - publishes a "voting_invite"
         │                                   on Redis, one channel per
         │                                   voting option key
         │                                 - sets status = "started"
         ▼
 5. Each voter, asynchronously,
    submits a vote:
    POST /submit-vote  or  NATS vote.submit
         │
         ▼
 6. VoteAcceptor                           - rejects duplicates, unknown
         │                                   tasks, tasks not "started",
         │                                   and (private) non-members
         │                                 - runs the PQT → qualified
         │                                 - checks whether evaluation
         │                                   should start
         │                                 - persists the vote
         ▼
 7. VotingEvaluationInitiator              private: every org_id has a
         │                                 qualified vote
         │                                 public: qualified votes
         │                                 >= duration (default 5)
         │                                 → launch Kubernetes Job
         ▼
 8. Evaluator job                          choice evaluation →
         │                                 (tie-breaker if > 1 winner) →
         │                                 post-award
         ▼
 9. VoteResultFinalizer                    report_json stored,
         │                                 status = "complete"
         ▼
10. ResultNotifier                         "voting_result" published on
                                            NATS, one subject per winner
```

Key behavioral notes:

- **Start is time-driven. Evaluation is vote-driven.** The scheduler starts
  a task once `scheduled_time` has passed. After that, no timer runs.
  Evaluation fires only when the vote threshold is met. A task that never
  gets enough qualified votes stays `"started"` indefinitely.
- **The scheduler polls once a minute.** A task starts up to 60 seconds after
  its `scheduled_time`.
- **Disqualified votes still count as "voted".** The duplicate check looks
  at every stored vote, qualified or not. A subject whose vote fails the PQT
  cannot vote again on that task.
- **PQT failures disqualify the vote.** If the PQT workflow raises, or if
  launching the evaluation job raises, the vote is stored with
  `qualified = false`. Neither failure is reported to the voter.
- **Voting stays open during evaluation.** Status changes to `"complete"`
  only when the evaluator job finishes. Until then, new votes are still
  accepted, but the job that is already running does not see them.
- **Messages are fire-and-forget.** Invitations use Redis pub/sub, so a
  subject that is not subscribed when the task starts never receives its
  invitation. Result notifications on NATS have the same property. The
  system keeps no delivery record. Compare the bidding system's
  `BidTaskResult`.

## 1.3 Access modes

Every task has a `social_task_access_type` of `"private"` or `"public"`.

### Private

The creator names the eligible voters up front in `org_ids`. A vote from
any other subject is rejected. Evaluation starts once **every** subject in
`org_ids` has a qualified vote on file. If even one listed voter never votes,
or that voter's vote is disqualified, the task never evaluates.

### Public

Any subject may vote. `org_ids` is not checked. Evaluation starts once the
number of qualified votes reaches `duration`, or 5 if `duration` is not set.

> `duration` is a **vote count**, not a time span. The name is historical.
> No service treats it as seconds.

Any other value of `social_task_access_type` is stored without validation.
The intake service then accepts votes as if the task were public, and the
task never evaluates.

## 1.4 Task status

| Status | Set by | Meaning |
|---|---|---|
| `"scheduled"` | the creator, in the create request | Waiting for `scheduled_time`. **The service does not set this for you.** |
| `"started"` | `VotingTaskInitiator` | Invitations sent, votes accepted |
| `"complete"` | `VoteResultFinalizer` | Evaluation finished, `report_json` stored |

A task created without `"status": "scheduled"` and a `scheduled_time` is
stored but never picked up by the scheduler, so it never starts.

The services also write `start_time` (when the task starts) and `end_time`
(when it completes) onto the task document. These fields are not part of the
dataclass, so they appear in raw queries but not in parsed objects.

## 1.5 Current implementation gaps

These gaps were found by reading the code. Each one blocks or changes the
flow in §1.2. Fix them, or work around them, before you rely on the system.

| # | Gap | Effect |
|---|---|---|
| 1 | `votes_submission/` and `evaluator_job/` use an older `schema.py`. In that version, `from_dict` is `Cls(**data)`, and the evaluation fields are strings named `voting_pqt_dsl`, `choice_evaluation_dsl`, `tie_breaker_dsl`, `post_awarding_dsl`, and `voting_message_request_creator_dsl`. | MongoDB returns every document with an `_id` key. The old `from_dict` does not accept `_id`, so every read fails with `TypeError`, and `POST /submit-vote` returns `400` for every vote. Even after that is fixed, the documents that the submission service writes contain `voting_pqt` (a dict, [§2.5](02-schema.md#25-function-spec)), not `voting_pqt_dsl`. |
| 2 | `VoteAcceptor` checks the evaluation trigger **before** it saves the current vote. | The vote that would complete the set is not counted. Public tasks evaluate on the vote after the threshold. Private tasks never evaluate, because the last listed voter's vote is never counted and nobody else can vote. |
| 3 | The Kubernetes Job is named after `social_task_id`, which has the form `task_1a2b3c4d`. | Kubernetes object names cannot contain `_`, so the Job is rejected. The exception is caught by the PQT block, and the vote that triggered evaluation is stored as `qualified = false`. |
| 4 | `VoteServers()` and the evaluator's `Initiator()` and `VoteResultFinalizer()` are built with the default `mongodb://localhost:27017`. They ignore `MONGO_URL`. The evaluator Job is not given `WORKFLOWS_API_URL`. | Vote intake and evaluation read a different database than the submission service unless MongoDB is on localhost. The evaluator calls `http://localhost:5001` for workflows. |
| 5 | Invitations go to one Redis channel per **voting option key**, not per `org_ids` entry. | Voters are not invited unless they are also options. This is the case in a peer election ([§7](07-using-in-agent-sdk.md)). |
| 6 | `scheduled_time` is compared to a naive `datetime.utcnow()`. | A `scheduled_time` with a UTC offset raises `TypeError` in the scheduler's refresh. One such task stops **every** task from being dispatched. A trailing `Z` is rejected at creation with `400` (Python 3.10 `fromisoformat`). |
| 7 | `POST /generic-query/<collection>` returns raw MongoDB documents. | `ObjectId` is not JSON-serializable, so any query that matches at least one document returns `400`. |
| 8 | If the invitation creator raises, or the subject spec is missing, the task status is not updated. | The task stays `"scheduled"`, and the scheduler retries it every 60 seconds, indefinitely. |
| 9 | `job_id` is never written. | The field is always absent. Find the Job by name (`social_task_id`) in the `votes-evaluation` namespace. |

---
[← Back to index](README.md) · [Next: Schema →](02-schema.md)
