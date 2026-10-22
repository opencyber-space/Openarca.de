# Social Choice Voting System

The voting system runs structured social-choice votes. A **creator** submits
a **social task** that describes what is being decided and lists the
**voting options**. At its scheduled time the task starts and **invitations**
go out. **Voters** submit **votes**, each vote passes a **pre-qualification
test (PQT)**, and once enough qualified votes are in, an **evaluation job**
runs the **choice evaluation**, an optional **tie-breaker**, and a
**post-award** step. It then stores a report and notifies the winners.

All decision logic (invitation content, vote qualification, counting, tie
resolution, post-award actions) lives in pluggable workflows and functions
hosted in an external **DSL workflow registry** or **function registry**.
The voting services handle state, timing, and message delivery.

The system is four services that share one MongoDB database:

| Service | Source | Port | Responsibility |
|---|---|---|---|
| Submission | `submission/` | `5000` | Task creation API, cron scheduler, voting invitations |
| Vote intake | `votes_submission/` | `8081` (REST), NATS `vote.submit` | Vote validation, PQT, evaluation trigger |
| Evaluator job | `evaluator_job/` | — (Kubernetes Job) | Choice evaluation, tie-breaker, post-award, report, result notifications |
| Query system | `query_system/` | `8082` (REST), `8765` (WebSocket) | Reports, status, task bundles, live streaming |

Source of truth for everything in this documentation set (paths relative to
`services/social_choice/`):

| File | Responsibility |
|---|---|
| `submission/core/schema.py` | `SocialTaskCoreData`, `SocialChoiceSubjectSpecInput`, `SocialChoiceEvaluationInput`, `Votes` dataclasses |
| `submission/core/submission.py` | `SubmissionParser`, `SocialTaskController`: request parsing and task creation |
| `submission/core/api.py` | Flask API for task creation and parsing |
| `submission/core/scheduler.py` | `CronScheduler`: finds scheduled tasks that are due |
| `submission/core/votes_request.py` | `VotingTaskInitiator`: starts tasks and publishes invitations |
| `submission/core/evaluators/` | `execute_functionality`: runs a function-registry function or a DSL workflow |
| `votes_submission/core/servers.py` | REST and NATS vote intake (`VoteServers`) |
| `votes_submission/core/vote_pre_check.py` | `VotingInitialChecker`, `VoteAcceptor`: validation and PQT |
| `votes_submission/core/votes_initiator.py` | `VotingEvaluationInitiator`: evaluation trigger and Kubernetes Job launch |
| `evaluator_job/core/dsl_flow_executor.py` | `DSLEvaluator`: choice evaluation, tie-breaker, post-award |
| `evaluator_job/core/finalizer.py` | `VoteResultFinalizer`, `ResultNotifier`: report and NATS notifications |
| `query_system/core/queries.py` | `QueriesManager`: read-side queries |
| `query_system/core/servers.py` | Query REST API and WebSocket live stream |

> **Implementation status.** Some parts of the code do not yet work end to
> end. The main reason is that the vote-intake and evaluator services still
> use an older version of the schema. [§1.5](01-concepts.md#15-current-implementation-gaps)
> lists each gap and its effect. Read it before you deploy.

## Contents

1. [Concepts](01-concepts.md): actors, lifecycle, private vs. public access, task status, implementation gaps
2. [Schema](02-schema.md): field references for the four entities, the function spec, the report, and storage
3. [APIs](03-apis.md): REST reference for creating tasks, submitting votes, and querying, plus the WebSocket live stream
4. [Functions to write](04-functions.md): contracts for the invitation, PQT, choice evaluation, tie-breaker, and post-award hooks, with reference implementations
5. [Messaging](05-messaging.md): how invitations reach subjects, how votes arrive over NATS, and how results are announced
6. [Using the system from Python](06-using-from-python.md): copy-paste helpers for every API, subscription, and the live stream
7. [Using the system in the agent SDK](07-using-in-agent-sdk.md): wiring voting into an agents-sdk agent, with a worked example
