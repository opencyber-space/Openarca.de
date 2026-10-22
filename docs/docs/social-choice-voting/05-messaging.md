[← Back to index](README.md)

# 5. Messaging: how subjects hear about votes

Where the bidding system routes every message through a delegate service,
the voting system publishes directly to two message buses:

| Message | Direction | Transport | Address |
|---|---|---|---|
| `voting_invite` | system → subjects | Redis pub/sub (`ORG_REDIS_URL`) | one channel per voting option key |
| vote submission | subjects → system | NATS (`ORG_NATS_URL`) | subject `vote.submit` |
| `voting_result` | system → subjects | NATS (`ORG_NATS_URL`) | one subject per winner |

Votes can also be submitted over REST ([§3.4](03-apis.md#34-how-to-submit-a-vote)),
and progress can be watched over the WebSocket live stream
([§3.6](03-apis.md#36-websocket-live-stream)).

## 5.1 Delivery guarantees

None. Redis pub/sub and core NATS both drop a message if no one is
subscribed when it is published. The system does not record what was sent,
retry, or wait for acknowledgements. Compare the bidding system's
`BidTaskResult`.

As a result:

- Subscribe **before** a task's `scheduled_time` to be sure you get the
  invitation.
- Treat invitations and results as hints. The source of truth is the query
  API: `GET /get-status/<id>` and `GET /get-report/<id>` ([§3.5](03-apis.md#35-query-endpoints)).

## 5.2 `voting_invite`: sent when a task starts

Published by `VotingTaskInitiator` when the scheduler starts a task
([§1.2](01-concepts.md#12-lifecycle-of-a-social-task) step 4), before the
status changes to `"started"`.

**Transport:** Redis `PUBLISH` on `ORG_REDIS_URL` (default
`redis://localhost:6379/0`). The same payload is published once on a channel
named after **each key of `voting_options_map`**.

```json
{
  "event_type": "voting_invite",
  "sender_subject_id": "planner-service",
  "event_data": {
    "custom_data": { "...": "invitation creator output, or {}" },
    "voting_info": {
      "social_task_id": "task_3f9c6d2e",
      "topic_title": "Lead translator, Q4 handbook",
      "topic_description": "Pick the agent that will lead the EN→FR translation of the Q4 handbook.",
      "voting_options_map": { "agent-translator-01": "Translator 01", "...": "..." },
      "voting_option_metadata_map": { "...": "..." },
      "supported_protocols": ["http"],
      "voting_message_request_creator": { "...": "..." }
    }
  }
}
```

| Field | Value |
|---|---|
| `event_type` | always `"voting_invite"` |
| `sender_subject_id` | the task's `created_by_subject_id` |
| `event_data.custom_data` | output of the invitation creator ([§4.2](04-functions.md#42-invitation-creator)), or `{}` |
| `event_data.voting_info` | the full subject spec. Read `social_task_id` from here to vote. |

The invitation does not include `org_ids`, the access type, or the goal. If a
recipient needs them, it fetches `GET /get-full-task-bundle/<id>`.

> **Who is invited.** Invitations go to the **option keys**, not to `org_ids`.
> If your options are candidate subjects and the voters are a different set
> of subjects, the voters are not invited. Tell them about the task another
> way. Invitations reach voters only when every voter is also an option, as
> in a peer election ([§7](07-using-in-agent-sdk.md)).
> See [§1.5 gap 5](01-concepts.md#15-current-implementation-gaps).

**Subscribing:**

```python
import json
import redis

r = redis.Redis.from_url("redis://org-redis:6379/0", decode_responses=True)
pubsub = r.pubsub()
pubsub.subscribe("agent-translator-01")      # your subject ID

for msg in pubsub.listen():
    if msg["type"] != "message":
        continue
    event = json.loads(msg["data"])
    if event.get("event_type") == "voting_invite":
        task_id = event["event_data"]["voting_info"]["social_task_id"]
        print("invited to", task_id)
```

## 5.3 Vote submission over NATS

The vote-intake service subscribes to the NATS subject **`vote.submit`** on
`ORG_NATS_URL` (default `nats://localhost:4222`). A message there is handled
exactly like `POST /submit-vote` ([§3.4](03-apis.md#34-how-to-submit-a-vote)),
and its body has the same six-field shape.

```python
import asyncio, json, uuid
from nats.aio.client import Client as NATS

async def vote():
    nc = NATS()
    await nc.connect(servers=["nats://org-nats:4222"])
    await nc.publish("vote.submit", json.dumps({
        "vote_id": str(uuid.uuid4()),
        "social_task_id": "task_3f9c6d2e",
        "submitter_subject_id": "agent-reviewer-01",
        "vote_data": {"selected_option": "agent-translator-02"},
        "submission_time": "2026-10-22T10:03:12",
        "qualified": False,
    }).encode())
    await nc.drain()

asyncio.run(vote())
```

There is **no reply**. A rejected or disqualified vote is only logged by the
service. To learn the outcome, query the vote afterwards
(`GET /get-full-task-bundle/<id>`), or use REST, which returns `qualified` and
any rejection message.

## 5.4 `voting_result`: sent after evaluation

Published by the evaluator job's `ResultNotifier` after the report is stored
([§1.2](01-concepts.md#12-lifecycle-of-a-social-task) step 10).

**Transport:** NATS `PUBLISH` on `ORG_NATS_URL`. The same payload is published
once on a subject named after **each winner**. Losers, voters, and the
creator are not notified.

```json
{
  "event_type": "voting_result",
  "task_id": "task_3f9c6d2e",
  "event_data": {
    "social_task_id": "task_3f9c6d2e",
    "winners": ["agent-translator-02"],
    "post_award_payload": { "...": "post-award hook output verbatim" }
  }
}
```

The payload is deliberately lean, like the bidding system's `bid_winner`.
Everything the winner needs to act on must be put into `post_award_payload`
by the post-award hook ([§4.6](04-functions.md#46-post-award)). The full
context is in `GET /get-report/<id>`.

Anyone else who needs the outcome, such as the creator, the voters, or a
dashboard, polls `GET /get-status/<id>` until it returns `"complete"`, or
watches the live stream ([§3.6](03-apis.md#36-websocket-live-stream)).

**Subscribing:**

```python
import asyncio, json
from nats.aio.client import Client as NATS

async def listen(subject_id: str):
    nc = NATS()
    await nc.connect(servers=["nats://org-nats:4222"])

    async def on_msg(msg):
        event = json.loads(msg.data.decode())
        if event.get("event_type") == "voting_result":
            print("won", event["task_id"], event["event_data"]["post_award_payload"])

    await nc.subscribe(subject_id, cb=on_msg)
    while True:
        await asyncio.sleep(1)

asyncio.run(listen("agent-translator-02"))
```

## 5.5 Sharing a bus with other traffic

Both buses address subjects by their bare subject ID: the Redis channel
`agent-translator-01` and the NATS subject `agent-translator-01`. Other systems
on the same Redis or NATS may use the same names. Always check `event_type`
before you act on a message, and ignore types you don't recognise.

---
[← Previous: Functions to write](04-functions.md) · [Back to index](README.md) · [Next: Using the system from Python →](06-using-from-python.md)
