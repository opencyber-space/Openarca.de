[← Back to index](README.md)

# 6. Using the Python client library

The client is a single file, `client/bidding_client.py`. It wraps the bidding
REST API ([§3](03-apis.md)) in dataclass inputs and outputs, and adds a
background poller for tagged bidding tasks.

It is standalone. The only third-party dependency is `requests`, and it does
not import anything from the server code. Copy the file into your project,
or put `client/` on `PYTHONPATH`.

```python
from bidding_client import (
    BiddingClient, BiddingError,
    BidSubmission, BidTagQuery, BidJob, Bid,
)
```

## 6.1 Quick reference

| Function | Input | Returns | Purpose |
|---|---|---|---|
| `BiddingClient.submit_bid` | `BidSubmission` | `Bid` | Submit a bid, or apply to an open-mode job |
| `BiddingClient.get_bid_job` | `str` (job ID) | `BidJob` | Query one bidding task by ID |
| `BiddingClient.find_bid_jobs_by_tags` | `BidTagQuery` | `List[BidJob]` | Query all bidding tasks matching the tags |
| `BiddingClient.poll_bid_tasks` | `BidTagQuery`, listener, interval | `BidTaskPoller` (started) | Background poll for tagged tasks; calls `listener.on_bidding_task(BidJob)` |

## 6.2 Creating the client

```python
client = BiddingClient(
    "http://orcade.internal:5000",   # required, always passed explicitly
    timeout=(5, 30),                 # optional: (connect, read) seconds
    session=None,                    # optional: your own requests.Session
)
```

- `base_url` is required. The client never reads environment variables. Your
  code decides where the URL comes from.
- A blank `base_url` raises `ValueError`. Omitting it raises `TypeError`.
- A trailing slash on `base_url` is stripped.

## 6.3 Dataclasses

The client accepts and returns these types. Every input is a dataclass, and
every output is a dataclass. The `bid_job_*` field names match the server
schema in [§2](02-schema.md).

### `BidSubmission` (input to `submit_bid`)

| Field | Type | Default | Notes |
|---|---|---|---|
| `bid_job_id` | `str` | required | Goes in the URL path, not the body |
| `bid_subject_id` | `str` | required | Your subject's ID |
| `bid_data` | `dict` | `{}` | Free-form; the PQT and evaluator functions read it |

### `Bid` (output of `submit_bid`)

| Field | Type | Notes |
|---|---|---|
| `bid_id` | `str` | |
| `bid_job_id` | `str` | |
| `bid_subject_id` | `str` | |
| `bid_data` | `dict` | |
| `submission_time` | `datetime \| None` | Parsed from ISO-8601 |
| `is_winner` | `bool` | Becomes `True` once the job is evaluated |

### `BidJob` (output of `get_bid_job`, `find_bid_jobs_by_tags`, and poller callbacks)

| Field | Type | Default |
|---|---|---|
| `bid_job_id` | `str` | required |
| `bid_job_name` | `dict` | `{}` |
| `bid_job_description` | `dict` | `{}` |
| `bid_job_metadata` | `dict` | `{}` |
| `bid_job_evaluator_id` | `str` | `""` |
| `bid_job_pqt_id` | `str` | `""` |
| `bid_job_tie_id` | `str` | `""` |
| `bid_job_creator_id` | `str` | `""` |
| `bid_job_subject_ids` | `List[str]` | `[]` |
| `bid_job_mode` | `str` | `"closed"` (`"open"` for open-mode jobs) |
| `bid_job_max_subjects` | `int \| None` | `None` |
| `bid_job_max_time` | `int \| None` | `None` (seconds) |
| `bid_job_status` | `str` | `"open"` |
| `bid_job_created_time` | `datetime \| None` | Parsed from ISO-8601 |
| `bid_job_closes_at` | `datetime \| None` | Parsed from ISO-8601 |
| `bid_job_tags` | `List[str]` | `[]` |

`BidJob.from_dict(d)` and `job.to_dict()` convert to and from the wire
format. You need `from_dict` when you receive a job embedded in another
payload, for example the `bid_job` field of a `bid_request` task
([§7.3](07-using-client-in-agent-sdk.md)).

### `BidTagQuery` (input to tag lookups and the poller)

| Field | Type | Default | Notes |
|---|---|---|---|
| `tags` | `List[str]` | required | At least one tag. Each tag must be non-empty and must not contain a comma |
| `match` | `str` | `"all"` | `"all"`: job has every tag. `"any"`: job has at least one |

Validation runs when the object is constructed, so bad input raises
`ValueError` immediately, before any network call.

## 6.4 Submitting a bid

```python
bid = client.submit_bid(BidSubmission(
    bid_job_id="8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10",
    bid_subject_id="agent-translator-01",
    bid_data={"price_usd": 120.0, "eta_hours": 6, "confidence": 0.92},
))
print(bid.bid_id, bid.is_winner)
```

For an open-mode job, the same call is an application. The subject is added
to the roster if the PQT function accepts the bid ([§1.3](01-concepts.md#13-bidding-modes)).

## 6.5 Querying a bidding task by ID

```python
job = client.get_bid_job("8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10")
print(job.bid_job_status, job.bid_job_subject_ids)
```

## 6.6 Querying bidding tasks by tag

```python
jobs = client.find_bid_jobs_by_tags(BidTagQuery(tags=["translation", "fr"]))
open_jobs = client.find_bid_jobs_by_tags(BidTagQuery(tags=["legal", "finance"], match="any"))
```

An empty result is `[]`. The search does not filter by status or mode.
Filter the returned list yourself if you need only open jobs.

## 6.7 Polling for tagged bidding tasks

`poll_bid_tasks` starts a daemon thread and returns a running
`BidTaskPoller`. The thread queries the server every `interval_seconds`. Each
new matching job is passed to `listener.on_bidding_task(bid_task_data)` as a
`BidJob`.

The listener is any object that has an `on_bidding_task` method. You don't
need to subclass anything.

```python
class TranslationAgent:
    def __init__(self, client: BiddingClient):
        self.client = client

    def on_bidding_task(self, bid_task_data: BidJob) -> None:
        if bid_task_data.bid_job_mode != "open":
            return
        self.client.submit_bid(BidSubmission(
            bid_job_id=bid_task_data.bid_job_id,
            bid_subject_id="agent-translator-01",
            bid_data={"price_usd": 110.0, "confidence": 0.9},
        ))


agent = TranslationAgent(client)
poller = client.poll_bid_tasks(
    BidTagQuery(tags=["translation"], match="any"),
    agent,
    interval_seconds=10,
)

# later, when shutting down:
poller.stop(timeout=5)
```

### Poller behavior

| Behavior | Detail |
|---|---|
| First poll | Delivers every matching job that already exists |
| Repeats | Each job is delivered at most once per poller |
| Filtering | `only_open=True` (default) skips jobs whose status is not `"open"`. Closed-mode jobs always read `"open"`, so they are still delivered. Pass `only_open=False` to receive closed open-mode jobs as well |
| Listener errors | Logged with the job ID. The job stays marked as delivered, and polling continues |
| Server or network errors | Logged. The poll is retried on the next interval |
| Thread | The listener runs on the poller thread. A slow listener delays the next poll |
| `running` | `True` while the thread is alive and `stop()` has not been called |
| `stop(timeout)` | Signals the thread to exit and waits up to `timeout` seconds. Does nothing if called from the poller thread |
| `poll_once()` | Runs one poll synchronously and returns how many jobs were delivered. Use it for manual or one-shot polling |

To drive polling yourself, build the poller without starting it, then call
`poll_once()` in your own loop:

```python
from bidding_client import BidTaskPoller

poller = BidTaskPoller(client, BidTagQuery(tags=["translation"]), agent, interval_seconds=10)
delivered = poller.poll_once()
```

## 6.8 Errors

Every server-side failure, and every failure to reach the server, raises
`BiddingError`.

```python
try:
    client.submit_bid(submission)
except BiddingError as e:
    print(e.status_code, e.message)
```

| `status_code` | Meaning | Typical cause |
|---|---|---|
| `400` | Invalid request | Subject not in a closed job's roster, blank tags, bad `match` |
| `404` | Not found | Unknown `bid_job_id` |
| `409` | Refused | PQT rejected the bid; open job is closed, full, past its deadline; subject already applied |
| `500` | Server error | Database failure or unexpected exception |
| `None` | No HTTP response | Connection refused, DNS failure, timeout |

`str(e)` gives `"[409] Subject 'x' has already applied to job '…'."` or, when
there is no status code, the underlying transport message.

The client does not retry. Retry policy belongs to the caller. Retrying a
`409` is pointless, since the refusal will repeat.

## 6.9 Thread safety

`BiddingClient` wraps a single `requests.Session`. The poller thread and your
own threads must not share one client, because `requests.Session` is not
guaranteed to be thread-safe.

Create one client per thread:

```python
poll_client = BiddingClient(url)   # handed to poll_bid_tasks
task_client = BiddingClient(url)   # used by your request handlers
```

## 6.10 Limitations

- **Job creation is not in the client.** Create jobs through the REST API
  ([§3.2](03-apis.md#32-how-to-create-a-bid-job)). The client covers the
  subject side only.
- **Tags may not contain commas.** The server splits the query parameter on
  commas.
- **Poller state is in memory.** If the process restarts, the poller
  redelivers every matching job that is still open. Make your listener
  idempotent. A repeat bid from the same subject is refused with `409` in
  both modes, so resubmitting is safe.
- **Seen-job tracking grows with time.** The poller stores one job ID per
  delivered job for its lifetime. This is negligible at normal volumes.
- **Closed-mode jobs look open.** Use `bid_job_subject_ids` and
  `bid_job_mode` to tell them apart in your listener.

---
[← Previous: Delegate system](05-delegate-system.md) · [Back to index](README.md) · [Next: Using the client in the agent SDK →](07-using-client-in-agent-sdk.md)
