[← Back to index](README.md)

# 6. Using the system from Python

The voting system does not ship a client library yet. Compare the bidding
system's `bidding_client.py`. This page provides a minimal, single-file
client that you can copy into your project. It wraps the REST APIs in
[§3](03-apis.md) and covers the invitation subscription from
[§5.2](05-messaging.md#52-voting_invite-sent-when-a-task-starts). Its only
dependencies are `requests` and, for the subscription, `redis`.

## 6.1 Quick reference

| Method | Server | Returns | Purpose |
|---|---|---|---|
| `VotingClient.create_task(payload)` | submission | `str` (task ID) | Create a social task ([§3.2](03-apis.md#32-how-to-create-a-social-task)) |
| `VotingClient.parse_task(payload)` | submission | `dict` | Validate a payload without storing it ([§3.3](03-apis.md#33-how-to-validate-a-task-without-creating-it)) |
| `VotingClient.submit_vote(task_id, subject_id, vote_data)` | vote intake | `bool` (qualified) | Cast a vote ([§3.4](03-apis.md#34-how-to-submit-a-vote)) |
| `VotingClient.get_status(task_id)` | query | `str \| None` | Current status |
| `VotingClient.get_report(task_id)` | query | `dict` | Final report (`{}` until complete) |
| `VotingClient.get_bundle(task_id)` | query | `dict` | Task, specs, and all votes |
| `VotingClient.wait_for_result(task_id, ...)` | query | `dict` | Poll until `"complete"`, then return the report |
| `InviteListener` | Redis | thread | Calls `listener.on_voting_invite(event)` for each invitation |

## 6.2 The client

Save as `voting_client.py`:

```python
# voting_client.py
import json
import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional

import requests

log = logging.getLogger(__name__)


class VotingError(Exception):
    def __init__(self, status_code: Optional[int], message: str):
        super().__init__(f"[{status_code}] {message}" if status_code else message)
        self.status_code = status_code
        self.message = message


class VotingClient:
    """Thin wrapper over the three voting HTTP servers. Not thread-safe:
    use one instance per thread."""

    def __init__(self, submission_url: str, intake_url: str, query_url: str,
                 timeout=(5, 30), session: Optional[requests.Session] = None):
        self.submission_url = submission_url.rstrip("/")
        self.intake_url = intake_url.rstrip("/")
        self.query_url = query_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

    # ---- transport ----

    def _request(self, method: str, url: str, **kwargs) -> Any:
        try:
            resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as e:
            raise VotingError(None, str(e)) from e
        try:
            body = resp.json()
        except ValueError:
            body = {"error": resp.text}
        if resp.status_code >= 400:
            msg = body.get("error", resp.text) if isinstance(body, dict) else resp.text
            raise VotingError(resp.status_code, msg)
        return body

    # ---- tasks ----

    def create_task(self, payload: Dict[str, Any]) -> str:
        body = self._request("POST", f"{self.submission_url}/submit-social-choice-task", json=payload)
        return body["social_task_id"]

    def parse_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", f"{self.submission_url}/parse-social-choice-task", json=payload)["parsed"]

    # ---- votes ----

    def submit_vote(self, social_task_id: str, submitter_subject_id: str,
                    vote_data: Dict[str, Any], vote_id: Optional[str] = None) -> bool:
        body = self._request("POST", f"{self.intake_url}/submit-vote", json={
            "vote_id": vote_id or str(uuid.uuid4()),
            "social_task_id": social_task_id,
            "submitter_subject_id": submitter_subject_id,
            "vote_data": vote_data,
            # required by the server's parser, then overwritten
            "submission_time": "1970-01-01T00:00:00",
            "qualified": False,
        })
        return bool(body["qualified"])

    # ---- queries ----

    def get_status(self, social_task_id: str) -> Optional[str]:
        return self._request("GET", f"{self.query_url}/get-status/{social_task_id}")["status"]

    def get_report(self, social_task_id: str) -> Dict[str, Any]:
        return self._request("GET", f"{self.query_url}/get-report/{social_task_id}")

    def get_bundle(self, social_task_id: str) -> Dict[str, Any]:
        return self._request("GET", f"{self.query_url}/get-full-task-bundle/{social_task_id}")

    def wait_for_result(self, social_task_id: str, *, interval_seconds: float = 10,
                        timeout_seconds: Optional[float] = None) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds if timeout_seconds else None
        while self.get_status(social_task_id) != "complete":
            if deadline and time.monotonic() > deadline:
                raise TimeoutError(f"task {social_task_id} not complete after {timeout_seconds}s")
            time.sleep(interval_seconds)
        return self.get_report(social_task_id)


class InviteListener(threading.Thread):
    """Subscribes to a subject's Redis channel and calls
    listener.on_voting_invite(event) for every voting_invite."""

    def __init__(self, redis_url: str, subject_id: str, listener):
        super().__init__(daemon=True, name=f"voting-invites-{subject_id}")
        import redis  # only needed for invitations
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._pubsub = self._redis.pubsub()
        self._pubsub.subscribe(subject_id)
        self._listener = listener
        self._stop = threading.Event()

    def run(self):
        while not self._stop.is_set():
            msg = self._pubsub.get_message(timeout=1.0)
            if not msg or msg["type"] != "message":
                continue
            try:
                event = json.loads(msg["data"])
            except ValueError:
                continue
            if event.get("event_type") != "voting_invite":
                continue
            try:
                self._listener.on_voting_invite(event)
            except Exception:
                log.exception("on_voting_invite failed")

    def stop(self, timeout: Optional[float] = None):
        self._stop.set()
        if threading.current_thread() is not self:
            self.join(timeout)
        self._pubsub.close()
```

Construct it with all three base URLs. The client never reads environment
variables, so your code decides where the URLs come from:

```python
from voting_client import VotingClient, VotingError, InviteListener

client = VotingClient(
    submission_url="http://voting-submission:5000",
    intake_url="http://voting-intake:8081",
    query_url="http://voting-query:8082",
)
```

`InviteListener` subscribes in its constructor, so it receives invitations
published from that moment on, even before `start()` is called. Messages are
then delivered once the thread starts.

## 6.3 Creating a task

```python
task_id = client.create_task({
    "social_task": {
        "created_by_subject_id": "planner-service",
        "created_by_subject_data": {},
        "org_ids": ["agent-reviewer-01", "agent-reviewer-02", "agent-reviewer-03"],
        "access_type": "private",
        "goal": {"objective": "Choose the lead translator"},
        "topics": ["translation"],
        "properties": {},
        "creation_time": "2026-10-22T09:00:00",
        "scheduled_time": "2026-10-22T10:00:00",   # naive, UTC
        "status": "scheduled",                       # required to start
    },
    "subject_spec": {
        "title": "Lead translator",
        "description": "Pick the lead translator.",
        "voting_options": {"agent-translator-01": "01", "agent-translator-02": "02"},
        "voting_metadata": {},
        "supported_protocols": ["http"],
        "voting_request": {},
    },
    "evaluation_spec": {
        "constraints_primary": "",
        "constraints_secondary": "",
        "voting_pqt": {"mode": "dsl", "workflow_id": "vote-option-is-valid:1.0"},
        "evaluation": {"mode": "dsl", "workflow_id": "plurality-count:1.0"},
        "tie_breaker": {},
        "post_award": {"mode": "dsl", "workflow_id": "assign-lead-translator:1.0"},
    },
})
```

To build `creation_time` and `scheduled_time` from `datetime` objects, use
`datetime.utcnow().replace(microsecond=0).isoformat()`. Do not use
`datetime.now(timezone.utc).isoformat()`: the offset it adds stalls the
scheduler ([§1.5 gap 6](01-concepts.md#15-current-implementation-gaps)).

## 6.4 Casting a vote

```python
try:
    qualified = client.submit_vote(task_id, "agent-reviewer-01",
                                   {"selected_option": "agent-translator-02"})
    print("stored; qualified =", qualified)
except VotingError as e:
    print("rejected:", e.message)
```

`submit_vote` generates a `vote_id` unless you pass one, and it fills in the
two placeholder fields the server requires.

## 6.5 Waiting for the result

```python
report = client.wait_for_result(task_id, interval_seconds=10, timeout_seconds=3600)
print(report["winners"], report["post_award_payload"])
```

To see progress while voting is open, use `get_bundle(task_id)["votes"]`, or
the WebSocket live stream ([§3.6](03-apis.md#36-websocket-live-stream)).

## 6.6 Receiving invitations

The listener is any object with an `on_voting_invite(event)` method:

```python
class Voter:
    def __init__(self, client, subject_id):
        self.client = client
        self.subject_id = subject_id

    def on_voting_invite(self, event):
        info = event["event_data"]["voting_info"]
        choice = next(iter(info["voting_options_map"]))   # replace with real logic
        self.client.submit_vote(info["social_task_id"], self.subject_id,
                                {"selected_option": choice})


invite_client = VotingClient(submission_url, intake_url, query_url)   # own client for this thread
listener = InviteListener("redis://org-redis:6379/0", "agent-reviewer-01",
                          Voter(invite_client, "agent-reviewer-01"))
listener.start()
# ...
listener.stop(timeout=5)
```

## 6.7 Errors

All HTTP failures and transport failures raise `VotingError`.

| `status_code` | Meaning | Typical cause |
|---|---|---|
| `400` | Rejected | Every vote rejection ([§3.4](03-apis.md#34-how-to-submit-a-vote)), a bad task payload, an unknown task ID on the query server |
| `500` | Server error | Missing nested key in a create request, database failure |
| `None` | No HTTP response | Connection refused, DNS failure, timeout |

The vote-intake and query servers return `400` for everything, so use
`e.message` to tell the cases apart. A disqualified vote is **not** an error:
`submit_vote` returns `False`.

The client does not retry. Retrying a rejected vote is pointless, because
duplicate votes are refused.

## 6.8 Thread safety

`VotingClient` wraps a single `requests.Session`, which is not guaranteed to
be thread-safe. Give each thread its own client. In particular, give
`InviteListener`'s callback a separate client from your main thread, as in
§6.6.

## 6.9 Limitations

- **Generic queries are not wrapped.** `POST /generic-query` currently fails
  on any non-empty result ([§1.5 gap 7](01-concepts.md#15-current-implementation-gaps)).
- **There is no task discovery.** Subjects learn about tasks through
  invitations or out of band. There is no tag search like the bidding
  system's `GET /bid-jobs/by-tags`.
- **NATS is not wrapped.** For NATS vote submission or result notifications,
  use `nats-py` directly ([§5.3](05-messaging.md#53-vote-submission-over-nats),
  [§5.4](05-messaging.md#54-voting_result-sent-after-evaluation)).
- **Invitations can be missed.** `InviteListener` only receives messages
  published while it is subscribed ([§5.1](05-messaging.md#51-delivery-guarantees)).

---
[← Previous: Messaging](05-messaging.md) · [Back to index](README.md) · [Next: Using the system in the agent SDK →](07-using-in-agent-sdk.md)
