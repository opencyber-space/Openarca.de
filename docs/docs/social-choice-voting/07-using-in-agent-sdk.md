[← Back to index](README.md)

# 7. Using the system in the agent SDK

This page shows how an agent built on the agents SDK
(`services/agents/libs/agents-sdk`) takes part in voting, using the client
from [§6](06-using-from-python.md). It covers the two things an agent does:

1. **Vote when invited.** The agent subscribes to its own Redis channel and
   casts a vote when a `voting_invite` arrives
   ([§5.2](05-messaging.md#52-voting_invite-sent-when-a-task-starts)).
2. **Act on a win.** The agent learns that it won and reads the
   post-award payload ([§5.4](05-messaging.md#54-voting_result-sent-after-evaluation)).

The voting system does not use the delegate service, so neither path goes
through the SDK's task queue or `on_data`. Both run on background threads
that the agent starts itself.

The worked example in [§7.6](#76-worked-example) is a **peer election**: a
group of agents elects one of themselves. Each agent is both a voter
(`org_ids`) and an option (a `voting_options_map` key). Today this is the
configuration in which invitations reach the voters
([§1.5 gap 5](01-concepts.md#15-current-implementation-gaps)).

## 7.1 How the SDK runs an agent

From the SDK source:

- An agent is a class with this shape:

  ```python
  class MyAgent:
      def __init__(self, subject, context: Context) -> None: ...
      def on_preprocess(self, task: AgentTask) -> Optional[List[AgentTask]]: ...
      def on_data(self, task: AgentTask) -> AgentResult: ...
  ```

- The file ends with `main(MyAgent)`. `main` reads `SUBJECT_ID`, loads the
  subject from `SUBJECT_DB_URL`, builds an `AgentExecutor`, and starts a
  Redis worker that reads tasks from `REDIS_STREAM` and calls `on_data` one
  at a time.
- `context.subject_id` is this subject's ID. Use it as
  `submitter_subject_id`, and as the Redis channel and NATS subject to
  listen on.

The SDK's `REDIS_URL` is the agent's **task queue**. The voting system
publishes invitations on the organisation's Redis (`ORG_REDIS_URL` on the
voting side). These can be the same server or different servers. Configure
them separately.

## 7.2 Adding the client to the SDK

Save the client from [§6.2](06-using-from-python.md#62-the-client) into the
SDK's `core` package:

```
services/agents/libs/agents-sdk/core/voting_client.py
```

```python
from core.voting_client import VotingClient, VotingError, InviteListener
```

`requests` and `redis` are already in the SDK's `requirements.txt`. Add
`nats-py` only if you use NATS for result notifications (§7.4).

### Environment variables

| Variable | Required | Read by | Purpose |
|---|---|---|---|
| `VOTING_SUBMISSION_URL` | if the agent creates tasks | your agent code | Submission server, e.g. `http://voting-submission:5000` |
| `VOTING_INTAKE_URL` | yes, if the agent votes | your agent code | Vote-intake server, e.g. `http://voting-intake:8081` |
| `VOTING_QUERY_URL` | yes | your agent code | Query server, e.g. `http://voting-query:8082` |
| `VOTING_REDIS_URL` | yes, if the agent votes | your agent code | The Redis server the voting system publishes invitations on |
| `VOTING_RESULT_POLL_SECONDS` | no (default `15`) | your agent code | How often to poll for results of tasks this agent voted in |
| `SUBJECT_ID` | yes | SDK | Subject identity |
| `SUBJECT_DB_URL`, `AGENT_DELEGATE_URL`, `REDIS_URL`, `REDIS_STREAM` | as for any SDK agent | SDK | See the SDK docs |

## 7.3 Pattern A: voting when invited

Start an `InviteListener` on `context.subject_id` in `__init__`. Its thread
calls `on_voting_invite` for each invitation:

```python
def on_voting_invite(self, event: dict) -> None:
    info = event["event_data"]["voting_info"]
    task_id = info["social_task_id"]
    choice = self._choose(info, event["event_data"].get("custom_data", {}))
    try:
        qualified = self._invite_client.submit_vote(
            task_id, self.subject_id, {"selected_option": choice})
        log.info("Voted %s on %s (qualified=%s)", choice, task_id, qualified)
        self._watch(task_id)
    except VotingError as e:
        log.info("Vote refused on %s: %s", task_id, e.message)
```

Timing matters: the invitation is published **before** the task's status
changes to `"started"` ([§5.2](05-messaging.md#52-voting_invite-sent-when-a-task-starts)).
A vote sent immediately can be rejected with `Voting task is not active yet.`
Retry that one message a few times with a short delay (§7.6 does this).

The listener must be subscribed when the task starts. An agent that boots
after `scheduled_time` misses the invitation
([§5.1](05-messaging.md#51-delivery-guarantees)).

## 7.4 Pattern B: learning the result

There are two options:

- **Poll** (no extra dependency). For each task the agent voted in, poll
  `GET /get-status/<id>` on a background thread until it returns
  `"complete"`, then read the report. Every voter learns the outcome this
  way, not just the winners. §7.6 uses this.
- **NATS** (winners only). Subscribe to `context.subject_id` on the
  organisation's NATS, and handle `voting_result` events
  ([§5.4](05-messaging.md#54-voting_result-sent-after-evaluation)). This
  needs `nats-py` and an asyncio loop on its own thread.

Either way, do not block `on_data` waiting for a vote to finish. The SDK
processes queued tasks one at a time, and a vote can take minutes or hours.

## 7.5 Threads and clients

Three threads may touch the voting system:

- the **invite listener** thread, which runs `on_voting_invite`
- the **result watcher** thread, which polls for status
- the SDK's **Redis worker** thread, if `on_data` creates tasks

Give each thread its own `VotingClient` ([§6.8](06-using-from-python.md#68-thread-safety)).
Build all of them, and set every attribute the callbacks use, **before** you
start the listener, because an invitation can arrive at once.

## 7.6 Worked example

A complete agent file for a peer election. Save it as `voting_agent.py` next
to the SDK's other sample agents. Replace `_choose` with your own decision
logic.

```python
# voting_agent.py
import logging
import os
import threading
import time
from typing import Dict, Set

from core.agent_executor import AgentTask, AgentResult, Context
from core.main import main
from core.voting_client import VotingClient, VotingError, InviteListener

log = logging.getLogger(__name__)


def _client() -> VotingClient:
    return VotingClient(
        submission_url=os.getenv("VOTING_SUBMISSION_URL", ""),
        intake_url=os.environ["VOTING_INTAKE_URL"],
        query_url=os.environ["VOTING_QUERY_URL"],
    )


class VotingAgent:

    def __init__(self, subject, context: Context) -> None:
        self.subject = subject
        self.context = context
        self.subject_id = context.subject_id

        # One client per thread.
        self._invite_client = _client()   # invite listener thread
        self._watch_client = _client()    # result watcher thread

        self._watching: Set[str] = set()
        self._lock = threading.Lock()
        self._poll_seconds = float(os.getenv("VOTING_RESULT_POLL_SECONDS", "15"))

        # Everything the callbacks use is set; now start the threads.
        self._watcher = threading.Thread(target=self._watch_loop, daemon=True,
                                         name="voting-results")
        self._watcher.start()
        self._listener = InviteListener(os.environ["VOTING_REDIS_URL"],
                                        self.subject_id, self)
        self._listener.start()

    # ---- pattern A: invitations (listener thread) ----

    def on_voting_invite(self, event: Dict) -> None:
        info = event["event_data"]["voting_info"]
        task_id = info["social_task_id"]
        choice = self._choose(info, event["event_data"].get("custom_data", {}))

        for attempt in range(5):
            try:
                qualified = self._invite_client.submit_vote(
                    task_id, self.subject_id, {"selected_option": choice})
                log.info("Voted %s on %s (qualified=%s)", choice, task_id, qualified)
                self._watch(task_id)
                return
            except VotingError as e:
                # The invite is published just before the task is marked
                # "started"; give the status update a moment to land.
                if "not active yet" in e.message and attempt < 4:
                    time.sleep(2)
                    continue
                log.info("Vote refused on %s: %s", task_id, e.message)
                return

    def _choose(self, info: Dict, custom_data: Dict) -> str:
        # Replace with real logic. Keys must match what the task's PQT and
        # choice-evaluation hooks expect.
        candidates = sorted(info["voting_options_map"])
        others = [c for c in candidates if c != self.subject_id]
        return (others or candidates)[0]

    # ---- pattern B: results (watcher thread) ----

    def _watch(self, task_id: str) -> None:
        with self._lock:
            self._watching.add(task_id)

    def _watch_loop(self) -> None:
        while True:
            time.sleep(self._poll_seconds)
            with self._lock:
                pending = list(self._watching)
            for task_id in pending:
                try:
                    if self._watch_client.get_status(task_id) != "complete":
                        continue
                    report = self._watch_client.get_report(task_id)
                except VotingError as e:
                    log.warning("Result poll failed for %s: %s", task_id, e)
                    continue
                with self._lock:
                    self._watching.discard(task_id)
                self._on_result(task_id, report)

    def _on_result(self, task_id: str, report: Dict) -> None:
        winners = report.get("winners", [])
        if self.subject_id in winners:
            log.info("Won %s: %s", task_id, report.get("post_award_payload"))
            # start whatever the post-award payload asks for
        else:
            log.info("Task %s decided: %s", task_id, winners)

    # ---- SDK task queue: unused by voting ----

    def on_preprocess(self, task: AgentTask):
        return [task]

    def on_data(self, task: AgentTask) -> AgentResult:
        return AgentResult(task_id=task.task_id, job_output={"ignored": True})


main(VotingAgent)
```

### Creating the election

Any service, or one of the agents, creates the task with the same IDs in
`org_ids` and as option keys:

```python
peers = ["agent-a", "agent-b", "agent-c"]
VotingClient(submission_url, intake_url, query_url).create_task({
    "social_task": {
        "created_by_subject_id": "agent-a",
        "created_by_subject_data": {},
        "org_ids": peers,
        "access_type": "private",
        "goal": {"objective": "Elect a coordinator"},
        "topics": ["election"],
        "properties": {},
        "creation_time": "2026-10-22T09:00:00",
        "scheduled_time": "2026-10-22T09:05:00",
        "status": "scheduled",
    },
    "subject_spec": {
        "title": "Coordinator election",
        "description": "Choose which peer coordinates the next run.",
        "voting_options": {p: p for p in peers},
        "voting_metadata": {},
        "supported_protocols": ["http"],
        "voting_request": {},
    },
    "evaluation_spec": {
        "constraints_primary": "",
        "constraints_secondary": "",
        "voting_pqt": {"mode": "dsl", "workflow_id": "vote-option-is-valid:1.0"},
        "evaluation": {"mode": "dsl", "workflow_id": "plurality-count:1.0"},
        "tie_breaker": {"mode": "dsl", "workflow_id": "earliest-vote-wins:1.0"},
        "post_award": {"mode": "dsl", "workflow_id": "announce-coordinator:1.0"},
    },
})
```

Start every agent before `09:05:00 UTC`, so that each one is subscribed when
the invitations go out.

### Testing without the full stack

`on_voting_invite` can be called directly with a fake event. Point
`VOTING_INTAKE_URL` at a test server or a mock:

```python
class FakeContext:
    subject_id = "agent-a"

agent = VotingAgent(subject=None, context=FakeContext())   # VOTING_* env vars must be set
agent.on_voting_invite({
    "event_type": "voting_invite",
    "sender_subject_id": "agent-a",
    "event_data": {
        "custom_data": {},
        "voting_info": {
            "social_task_id": "task_test0001",
            "voting_options_map": {"agent-a": "a", "agent-b": "b"},
        },
    },
})
```

## 7.7 Operational notes

- **Idempotency.** Each subject can vote once per task. A repeated invitation,
  for example from a retried task start ([§1.5 gap 8](01-concepts.md#15-current-implementation-gaps)),
  produces `Vote already submitted for this task.`, which the example logs
  and ignores.
- **Refusals are not errors.** A `VotingError` from `submit_vote` means the
  task moved on or the vote was not allowed. It does not mean the agent is
  broken. A disqualified vote is not an error either.
- **Watched tasks are in memory.** After a restart, the agent no longer polls
  tasks it voted in before. If outcomes matter across restarts, persist the
  task IDs, or query `votes` by `submitter_subject_id` once
  [§1.5 gap 7](01-concepts.md#15-current-implementation-gaps) is fixed.
- **Shutdown.** The SDK's `main` stops its Redis worker on SIGINT or SIGTERM,
  but it does not know about the listener or the watcher. Both are daemon
  threads, so the process exits without waiting for them. Call
  `self._listener.stop(timeout=5)` from a `signal` handler if you need a
  clean unsubscribe.

---
[← Previous: Using the system from Python](06-using-from-python.md) · [Back to index](README.md)
