[← Back to index](README.md)

# 7. Using the client in the agent SDK

This page shows how an agent built on the agents SDK
(`services/agents/libs/agents-sdk`) uses the bidding client
([§6](06-using-client-library.md)) to take part in bidding. It covers two
ways an agent learns about a bidding task:

1. **Delegated tasks**: Orcade calls the agent with a `bid_request` (closed
   mode) or a `bid_winner`, through the delegate system
   ([§5](05-delegate-system.md)).
2. **Polled tasks**: the agent polls for tagged open-mode jobs and applies to
   the ones it wants.

Most agents use one pattern or the other. The worked example in
[§7.6](#76-worked-example) uses both.

## 7.1 How the SDK runs an agent

From the SDK source:

- An agent is a class with this shape:

  ```python
  class MyAgent:
      def __init__(self, subject, context: Context) -> None: ...
      def on_preprocess(self, task: AgentTask) -> Optional[List[AgentTask]]: ...
      def on_data(self, task: AgentTask) -> AgentResult: ...
      def on_event(self, event_name: str, event_data: dict) -> None: ...  # optional
  ```

- The file ends with `main(MyAgent)`. `main` reads `SUBJECT_ID`, loads the
  subject from `SUBJECT_DB_URL`, and builds an `AgentExecutor`. The executor
  creates your agent with `(subject, context)`.
- `on_preprocess` runs first. Returning `None` skips the task. Returning
  `[task]` sends it to `on_data`.
- `on_data` returns an `AgentResult`. If it raises, the SDK wraps the
  exception in an error result. The worker keeps running.
- Tasks come from a Redis list (`REDIS_URL`, `REDIS_STREAM`). A single worker
  thread reads them with `BRPOP` and processes one at a time. Anything slow
  in `on_data` blocks every task behind it.

What the agent gets from `context`:

| Attribute | Source | Use for bidding |
|---|---|---|
| `context.subject_id` | `SUBJECT_ID` env var | This subject's ID. Use it as `bid_subject_id` |
| `context.delegator` | `AGENT_DELEGATE_URL` | Delegation to other subjects. Not needed for bidding |
| `context.p2p_manager` | Built-in mesh | Not needed for bidding |

What the agent gets from `subject`:

| Attribute | Use for bidding |
|---|---|
| `subject.metadata.subject_search_tags` | Tags to poll with. Tag bidding tasks the same way you tag subjects |
| `subject.identity.subject_id` | Same value as `context.subject_id` |

## 7.2 Adding the client to the SDK

The client is one file with no dependencies beyond `requests`, which the SDK
already lists in `requirements.txt`. Copy it into the SDK's `core` package:

```bash
cp services/orcade/client/bidding_client.py \
   services/agents/libs/agents-sdk/core/bidding_client.py
```

Import it the way the sample agents import the SDK:

```python
from core.bidding_client import BiddingClient, BiddingError, BidJob, BidSubmission, BidTagQuery
```

If you would rather not copy the file, put `services/orcade/client` on
`PYTHONPATH` and import `bidding_client` directly. Copying is preferable when
the agent is packaged into a container, because the file then travels with
the image.

### Environment variables

The client takes its URL as a constructor argument and never reads the
environment. Your agent reads the variable and passes the value in.

| Variable | Required | Read by | Purpose |
|---|---|---|---|
| `ORCADE_URL` | yes, if the agent bids | your agent code | Base URL of the Orcade service, e.g. `http://orcade-svc.orcade:5000` |
| `ORCADE_POLL_SECONDS` | no (default `10`) | your agent code | Poll interval for tagged open jobs |
| `SUBJECT_ID` | yes | SDK | Subject identity, used as `bid_subject_id` |
| `SUBJECT_DB_URL` | yes | SDK | Where the subject record is loaded from |
| `AGENT_DELEGATE_URL` | yes | SDK | Required by `Context`. Raises `ValueError` if empty |
| `REDIS_URL` | no (default `redis://localhost:6379/0`) | SDK | Task queue |
| `REDIS_STREAM` | no (default `jobs:inbox`) | SDK | Task queue key |

Set `ORCADE_URL` in the agent's Docker or Kubernetes configuration, next to
the other variables.

## 7.3 Pattern A: responding to delegated bidding tasks

When a closed-mode job is created, Orcade sends each eligible subject a
`bid_request` through the delegate ([§5.2](05-delegate-system.md#52-bid_request-sent-on-job-creation)).
When the job is evaluated, the winner receives a `bid_winner`
([§5.3](05-delegate-system.md#53-bid_winner-sent-after-evaluation)).

The SDK delivers these to `on_data` as an `AgentTask`. Orcade's `task_data`
is what the agent sees in `task.job_data`:

```python
# task.job_data for a bid_request
{
    "type": "bid_request",
    "bid_job": { "...": "full BidJob dict" },
    "bid_job_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10",
}

# task.job_data for a bid_winner
{
    "type": "bid_winner",
    "bid_job_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10",
    "result_data": { "...": "the evaluator's result_data" },
}
```

> **Verify before relying on this.** The SDK reads `task.job_data` from the
> Redis message. Orcade posts `task_data` to the delegate's
> `/api/submit-and-wait`. The delegate service is not in this repository, so
> I could not confirm how it wraps `task_data` into the Redis message. Confirm
> that `job_data` equals `task_data` with the delegate team before shipping.

Handling a `bid_request` in `on_data`:

```python
def on_data(self, task: AgentTask) -> AgentResult:
    kind = task.job_data.get("type")

    if kind == "bid_request":
        job = BidJob.from_dict(task.job_data["bid_job"])
        bid = self._bid(job, client=self._task_client)
        return AgentResult(
            task_id=task.task_id,
            job_output={"bid_id": bid.bid_id} if bid else {"accepted": False},
        )

    if kind == "bid_winner":
        return AgentResult(
            task_id=task.task_id,
            job_output={"acknowledged": True},
        )

    return AgentResult(
        task_id=task.task_id,
        is_error=True,
        error_data={"stage": "on_data", "message": f"unknown task type {kind!r}"},
    )
```

Submit the bid inside `on_data`, before returning. Orcade records whatever
the delegate returns as a task result ([§5.4](05-delegate-system.md#54-what-orcade-does-with-the-subjects-response)),
but nothing else is confirmed. The bid is not complete until `submit_bid`
returns.

Orcade waits up to 300 seconds for the delegate to respond. Because the Redis
worker processes tasks one at a time, keep `on_data` short.

## 7.4 Pattern B: polling for open-mode bidding tasks

Open-mode jobs send no `bid_request` ([§1.3](01-concepts.md#13-bidding-modes)).
Agents find them by polling for their tags. The poller thread calls the
agent's `on_bidding_task` method, which submits the bid.

```python
poll_client = BiddingClient(os.environ["ORCADE_URL"])
poller = poll_client.poll_bid_tasks(
    BidTagQuery(tags=subject.metadata.subject_search_tags, match="any"),
    self,                     # object with on_bidding_task
    interval_seconds=float(os.getenv("ORCADE_POLL_SECONDS", "10")),
)
```

The listener method receives a `BidJob`. For the threading reason in
[§7.5](#75-threads-and-clients), use a separate client for submitting from
the poller thread:

```python
def on_bidding_task(self, bid_task_data: BidJob) -> None:
    if bid_task_data.bid_job_mode != "open":
        return  # closed-mode jobs are handled through delegated bid_request tasks
    self._bid(bid_task_data, client=self._poll_client)
```

## 7.5 Threads and clients

Two threads can submit bids:

- The **Redis worker thread** runs `on_data` for delegated tasks.
- The **poller thread** runs `on_bidding_task` for polled jobs.

Give each thread its own `BiddingClient`, so they never share a
`requests.Session` ([§6.9](06-using-client-library.md#69-thread-safety)):

```python
self._task_client = BiddingClient(orcade_url)   # used by on_data
self._poll_client = BiddingClient(orcade_url)   # used by the poller and on_bidding_task
```

Both clients must be built before the poller starts, because the poller
can call `on_bidding_task` right away.

## 7.6 Worked example

This is a complete agent file that handles both patterns. Save it as
`bidding_agent.py` next to the SDK's other sample agents. Replace `_bid_data`
with your own pricing logic.

```python
# bidding_agent.py
import logging
import os
from typing import Optional

from core.agent_executor import AgentTask, AgentResult, Context
from core.main import main
from core.bidding_client import (
    BiddingClient, BiddingError, BidJob, BidSubmission, BidTagQuery, Bid,
)

log = logging.getLogger(__name__)


class BiddingAgent:

    def __init__(self, subject, context: Context) -> None:
        self.subject = subject
        self.context = context
        self.subject_id = context.subject_id

        orcade_url = os.environ["ORCADE_URL"]
        self._task_client = BiddingClient(orcade_url)   # Redis thread
        self._poll_client = BiddingClient(orcade_url)   # poller thread

        # Start polling before __init__ returns. Build every client first.
        tags = list(getattr(getattr(subject, "metadata", None), "subject_search_tags", []) or [])
        self._poller = None
        if tags:
            self._poller = self._poll_client.poll_bid_tasks(
                BidTagQuery(tags=tags, match="any"),
                self,
                interval_seconds=float(os.getenv("ORCADE_POLL_SECONDS", "10")),
            )

    # ---- pattern B: polled open-mode jobs (poller thread) ----

    def on_bidding_task(self, bid_task_data: BidJob) -> None:
        if bid_task_data.bid_job_mode != "open":
            return
        self._bid(bid_task_data, client=self._poll_client)

    # ---- pattern A: delegated tasks (Redis thread) ----

    def on_preprocess(self, task: AgentTask):
        return [task]

    def on_data(self, task: AgentTask) -> AgentResult:
        kind = task.job_data.get("type")
        try:
            if kind == "bid_request":
                job = BidJob.from_dict(task.job_data["bid_job"])
                bid = self._bid(job, client=self._task_client)
                output = {"bid_id": bid.bid_id} if bid else {"accepted": False}
                return AgentResult(task_id=task.task_id, job_output=output)

            if kind == "bid_winner":
                log.info("Won bid job %s", task.job_data.get("bid_job_id"))
                return AgentResult(
                    task_id=task.task_id,
                    job_output={"acknowledged": True},
                )

            return AgentResult(
                task_id=task.task_id,
                is_error=True,
                error_data={"stage": "on_data", "message": f"unknown task type {kind!r}"},
            )
        except Exception as e:
            log.exception("on_data failed for task %s", task.task_id)
            return AgentResult(
                task_id=task.task_id,
                is_error=True,
                error_data={"stage": "on_data", "message": str(e)},
            )

    # ---- shared ----

    def _bid(self, job: BidJob, *, client: BiddingClient) -> Optional[Bid]:
        """Submit this subject's bid. Returns None if Orcade refuses it (409)."""
        try:
            bid = client.submit_bid(BidSubmission(
                bid_job_id=job.bid_job_id,
                bid_subject_id=self.subject_id,
                bid_data=self._bid_data(job),
            ))
            log.info("Bid %s submitted to job %s", bid.bid_id, job.bid_job_id)
            return bid
        except BiddingError as e:
            if e.status_code == 409:
                log.info("Bid refused for job %s: %s", job.bid_job_id, e.message)
                return None
            raise

    def _bid_data(self, job: BidJob) -> dict:
        # Replace with real pricing logic. Keys must match what the job's
        # PQT and evaluator functions expect.
        return {"price_usd": 100.0, "confidence": 0.9}


main(BiddingAgent)
```

### Testing without the full stack

`on_data` can be exercised directly. Build the agent with a fake context and
feed it an `AgentTask`:

```python
from core.agent_executor import AgentTask

class FakeContext:
    subject_id = "agent-translator-01"

agent = BiddingAgent(subject=None, context=FakeContext())   # ORCADE_URL must be set
task = AgentTask(task_id="t-1", job_data={
    "type": "bid_request",
    "bid_job": job_dict,            # a BidJob.to_dict() from a test job
    "bid_job_id": job_dict["bid_job_id"],
})
result = agent.on_data(task)
assert not result.is_error
```

`subject=None` works here because the constructor tolerates a missing subject
(`getattr` guards the tag lookup), so no poller starts when no tags are
available.

## 7.7 Operational notes

- **Idempotency.** Both patterns can reach the same job. A closed-mode job
  sends `bid_request`, and the poller may also see it if its tags match and
  `bid_job_mode` is `"open"`. The mode check in `on_bidding_task` prevents
  that. Restarts also redeliver open jobs to the poller. A repeat application
  returns `409`, which `_bid` treats as "already bid".
- **Refusals are not errors.** A `409` means the job moved on (full, closed,
  or already applied). `_bid` returns `None`, so the agent does not report an
  error for it.
- **Unexpected bidding errors.** A `400` or `404` raises out of `_bid`. In
  `on_data` that becomes an error result. In the poller it is logged by
  `BidTaskPoller`.
- **Startup order.** `__init__` starts the poller, and the poller can call
  `on_bidding_task` at once. Set every attribute `on_bidding_task` uses before
  the poller starts.
- **Shutdown.** The SDK's `main` stops the Redis worker on SIGINT or SIGTERM,
  but it does not know about the poller. Stop the poller yourself, for
  example by registering a `signal` handler that calls
  `self._poller.stop(timeout=5)`. Poller threads are daemon threads, so
  process exit does not wait for them.

## 7.8 Observations about the SDK

These came up while reading the SDK for this guide. Neither is fixed here.

- `AgentDelegator.close()` in `core/delegate.py` refers to `self.session`,
  but the constructor never sets it, so calling `close()` raises
  `AttributeError`. It does not affect bidding because nothing calls `close()`
  today.
- `core/input_streams/redis_listener.py` is a separate, generic BRPOP worker.
  The live path is `start_redis_listener` in `core/utils.py`, which the
  bidding flow relies on.

---
[← Previous: Using the client library](06-using-client-library.md) · [Back to index](README.md)
