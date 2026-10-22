[← Back to index](README.md)

# 4. Functions to write (PQT & Evaluator)

PQT and evaluator "functions" are **not code inside Orcade**. They are
entries in an external function registry (`FUNCTION_REGISTRY_URL`),
referenced from a `BidJob` purely by `function_id` string
(`bid_job_pqt_id`, `bid_job_evaluator_id`). Orcade resolves and invokes them
through `FunctionCaller` (`core/functions.py`) → `AgentFunctions`
(`core/agents_functions/__init__.py`), which supports three execution
modes per `FunctionEntry`:

- **external** (`is_external=True`) — a plain HTTP `POST` to
  `external_function_url` with `external_headers`; the response's `"data"`
  key (or the whole JSON body if there's no `"data"` key) is returned. This
  is the simplest mode to target when writing a new PQT/evaluator — just
  stand up an HTTP endpoint.
- **stateful** (`is_stateful=True`) — the registry deploys the function as a
  long-lived service on first use (deployment is cached by
  `function_id` for the lifetime of the Orcade process) and subsequent
  calls hit that deployment.
- **stateless** — run once per call as a registry-managed job.

Regardless of mode, **every function receives a single JSON object as
input and must return a single JSON object as output.** Orcade does not
retry, validate, or interpret the response beyond the specific keys
documented below — malformed responses surface as `KeyError`/`None`s that
propagate as `500`s (for PQT, inline in the `submit_bid` request) or as a
logged error with no winner ever chosen (for the evaluator, since it runs
on a background thread).

## 4.1 Authoring format: `AIOSv1PolicyRule`

For **stateful** and **stateless** functions, the registry doesn't run
arbitrary scripts — it instantiates a fixed class from your
`function_code` and drives it through a fixed contract. Both the PQT
function and the evaluator function are written the same way, as a class
named exactly `AIOSv1PolicyRule`:

```python
import logging


class AIOSv1PolicyRule:

    def __init__(self, rule_id, settings, parameters):
        """
        Initializes an AIOSv1PolicyRule instance.

        Args:
            rule_id (str): Unique identifier for the rule.
            settings (dict): Configuration settings for the rule.
            parameters (dict): Parameters defining the rule's behavior.
        """
        self.rule_id = rule_id
        self.settings = settings
        self.parameters = parameters

    def eval(self, parameters, input_data, context):
        logging.info("input: {}".format(input_data))
        # ... decide, transform, return a dict
```

How each piece maps onto Orcade's bidding flow:

| Piece | Where it comes from | What it holds here |
|---|---|---|
| `rule_id` (constructor) | Set by the registry to the function's own `function_id` | Same string as `bid_job_pqt_id` / `bid_job_evaluator_id` — useful for logging which rule is running. |
| `settings` / `parameters` (constructor) | The `function_settings` / `function_parameters` dicts stored on the `FunctionEntry` at registration time | **Static, per-function configuration** — e.g. a PQT's minimum confidence threshold, or an evaluator's tie-break weighting. This is where you put tunables; it is not per-bid data. The registry typically instantiates the class once (especially for a stateful deployment) and reuses it across many `eval()` calls, so treat `__init__` as one-time setup. |
| `input_data` (`eval`) | The `input_data` dict Orcade builds in `BiddingService` and passes to `FunctionCaller.call(function_id=..., input_data=...)` | Exactly the PQT input contract (§4.2) or evaluator input contract (§4.3) below — i.e. `{"bid_job": ..., "bid": ...}` or `{"bid_job": ..., "bids": [...]}`. |
| `parameters` (`eval`) | The optional `parameters=` kwarg on `FunctionCaller.call()` / `AgentFunctions.call()` | `BiddingService` never passes this today (it only ever calls with `function_id` and `input_data`), so for PQT/evaluator calls this argument arrives empty — read configuration from `self.parameters` (set in `__init__`) instead of this per-call `parameters` argument. |
| `context` (`eval`) | Injected by the function-execution runtime itself | Opaque from Orcade's point of view — its shape is owned by the function platform, not by this service, and nothing in `core/bidding.py` depends on it. |
| return value (`eval`) | — | A plain JSON-serializable `dict`. This is exactly the response `BiddingService` reads `"accepted"` from (PQT) or `"winner_subject_id"` / `"status"` / `"result_data"` from (evaluator). |

If the function is instead registered with `is_external=True`, this class
contract doesn't apply — the registry just does a plain HTTP `POST` of the
same `input_data` JSON to `external_function_url` and expects a JSON body
back (optionally wrapped in a `"data"` key). Any HTTP service that honors
the input/output contracts below works there, in any language — a Flask
example for that mode is included alongside each `AIOSv1PolicyRule`
example below.

## 4.2 PQT (pre-qualification test) function

**Purpose:** gate-keep an individual bid the moment it's submitted, before
it's persisted — e.g. reject bids that are incomplete, out of budget, or
from a subject that failed some external eligibility check.

**When it's called:** inline, synchronously, inside `POST
/bid-jobs/{id}/bids`, once per bid, only if `bid_job_pqt_id` is non-empty.

**Input contract:**

```json
{
  "bid_job": { "...": "full BidJob.to_dict()" },
  "bid": { "...": "full Bid.to_dict(), submission_time already serialized to ISO string" }
}
```

**Output contract:**

| Key | Type | Required | Meaning |
|---|---|---|---|
| `accepted` | `boolean` | **yes** | Truthy → bid is persisted normally. Falsy/missing → bid is rejected, `submit_bid` raises `BidRejectedError`, HTTP caller gets `409`, nothing is written to the `bids` collection. |
| *(anything else)* | any | no | Ignored by Orcade today; free to add a `reason` field for your own logging/debugging, it just won't be surfaced back to the API caller. |

**Example input** (as delivered to the function):

```json
{
  "bid_job": {
    "bid_job_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10",
    "bid_job_metadata": {"max_budget_usd": 150},
    "bid_job_description": {"task_type": "translate_document"},
    "bid_job_name": {"en": "Translate Q3 report to French"},
    "bid_job_evaluator_id": "lowest-cost-evaluator:1.0-stable",
    "bid_job_pqt_id": "min-confidence-pqt:1.0-stable",
    "bid_job_tie_id": "",
    "bid_job_creator_id": "planner-service",
    "bid_job_subject_ids": ["agent-translator-01", "agent-translator-02"]
  },
  "bid": {
    "bid_id": "3c7c3e2a-2d1a-4e2d-9a3b-6d2f9e6b0d4c",
    "bid_job_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10",
    "bid_data": {"price_usd": 120.0, "eta_hours": 6, "confidence": 0.92},
    "bid_subject_id": "agent-translator-01",
    "submission_time": "2026-09-09T10:15:32.481203",
    "is_winner": false
  }
}
```

**Example output (accept):**
```json
{ "accepted": true }
```

**Example output (reject):**
```json
{ "accepted": false, "reason": "confidence 0.42 below required minimum 0.70" }
```

**Reference implementation** (`AIOSv1PolicyRule`, for a stateful or
stateless function — see [§4.1](#41-authoring-format-aiosv1policyrule)):

```python
import logging


class AIOSv1PolicyRule:

    def __init__(self, rule_id, settings, parameters):
        self.rule_id = rule_id
        self.settings = settings
        self.parameters = parameters

    def eval(self, parameters, input_data, context):
        logging.info("pqt input: {}".format(input_data))

        bid = input_data["bid"]
        confidence = bid.get("bid_data", {}).get("confidence", 0)
        min_confidence = self.settings.get("min_confidence", 0.70)

        if confidence < min_confidence:
            return {
                "accepted": False,
                "reason": f"confidence {confidence} below required minimum {min_confidence}",
            }

        return {"accepted": True}
```

`min_confidence` here comes from `self.settings`, i.e. whatever
`function_settings` was registered for `min-confidence-pqt:1.0-stable` —
change the threshold by updating the registry entry, not the code.

**Alternative reference implementation** (external HTTP mode,
`is_external=True` — any framework works, this uses Flask):

```python
from flask import Flask, request, jsonify

app = Flask(__name__)
MIN_CONFIDENCE = 0.70

@app.post("/")
def pqt():
    payload = request.get_json()
    bid = payload["bid"]
    confidence = bid["bid_data"].get("confidence", 0)

    if confidence < MIN_CONFIDENCE:
        return jsonify({"data": {
            "accepted": False,
            "reason": f"confidence {confidence} below required minimum {MIN_CONFIDENCE}",
        }})

    return jsonify({"data": {"accepted": True}})
```

## 4.3 Evaluator function

**Purpose:** given the job and the complete set of bids, decide the winner.

**When it's called:**

- **Closed mode:** once per job, on a background thread, the moment the last
  required subject's bid is persisted. The bids cover every entry in
  `bid_job_subject_ids`.
- **Open mode:** once per job, on a background thread, when the job closes
  (last slot filled, or deadline passed). The bids cover the final roster,
  which is every applicant that passed PQT. The evaluator is not called if
  there were no applicants.

In open mode, `bid_job.bid_job_status` is `"closed"` in the input, because
closing happens before evaluation. Closed-mode jobs never change status, so it
stays `"open"`. In both modes, `bid_job.bid_job_subject_ids` is the final
roster.

**Input contract:**

```json
{
  "bid_job": { "...": "full BidJob.to_dict()" },
  "bids": [ { "...": "full Bid.to_dict()" }, "... one per eligible subject" ]
}
```

**Output contract:**

| Key | Type | Required | Meaning |
|---|---|---|---|
| `winner_subject_id` | `string` | **yes** | Must equal the `bid_subject_id` of exactly one of the bids in the input. If it doesn't match any bid, Orcade logs an error and evaluation ends with **no winner set and no notification sent**. |
| `status` | `string` | no | Free-form status label, logged for observability (e.g. `"resolved"`, `"no_valid_bids"`). Not otherwise interpreted. |
| `result_data` | `object` | no (defaults to `{}`) | Arbitrary payload forwarded verbatim to the winning subject as part of its `bid_winner` task (see [§5.3](05-delegate-system.md#53-bid_winner-sent-after-evaluation)). Good place for things like the agreed price, start time, or evaluator rationale. |

**Example input:**

```json
{
  "bid_job": {
    "bid_job_id": "8f14e45f-ceea-4a19-8f6e-8b5a9c1a9f10",
    "bid_job_evaluator_id": "lowest-cost-evaluator:1.0-stable",
    "bid_job_pqt_id": "min-confidence-pqt:1.0-stable",
    "bid_job_subject_ids": ["agent-translator-01", "agent-translator-02"],
    "...": "remaining BidJob fields"
  },
  "bids": [
    {
      "bid_id": "3c7c3e2a-2d1a-4e2d-9a3b-6d2f9e6b0d4c",
      "bid_subject_id": "agent-translator-01",
      "bid_data": {"price_usd": 120.0, "eta_hours": 6, "confidence": 0.92},
      "...": "remaining Bid fields"
    },
    {
      "bid_id": "9d1e2f3a-4b5c-6d7e-8f90-1a2b3c4d5e6f",
      "bid_subject_id": "agent-translator-02",
      "bid_data": {"price_usd": 95.0, "eta_hours": 10, "confidence": 0.81},
      "...": "remaining Bid fields"
    }
  ]
}
```

**Example output:**

```json
{
  "winner_subject_id": "agent-translator-02",
  "status": "resolved",
  "result_data": {
    "reason": "lowest price among bids meeting confidence threshold",
    "agreed_price_usd": 95.0,
    "start_by": "2026-09-10T09:00:00Z"
  }
}
```

**Reference implementation** (`AIOSv1PolicyRule`, lowest-price-wins
evaluator, for a stateful or stateless function):

```python
import logging


class AIOSv1PolicyRule:

    def __init__(self, rule_id, settings, parameters):
        self.rule_id = rule_id
        self.settings = settings
        self.parameters = parameters

    def eval(self, parameters, input_data, context):
        logging.info("evaluator input: {}".format(input_data))

        bids = input_data["bids"]
        winner = min(bids, key=lambda b: b["bid_data"]["price_usd"])

        return {
            "winner_subject_id": winner["bid_subject_id"],
            "status": "resolved",
            "result_data": {
                "reason": "lowest price",
                "agreed_price_usd": winner["bid_data"]["price_usd"],
            },
        }
```

**Alternative reference implementation** (external HTTP mode,
`is_external=True`):

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.post("/")
def evaluate():
    payload = request.get_json()
    bids = payload["bids"]

    winner = min(bids, key=lambda b: b["bid_data"]["price_usd"])

    return jsonify({"data": {
        "winner_subject_id": winner["bid_subject_id"],
        "status": "resolved",
        "result_data": {
            "reason": "lowest price",
            "agreed_price_usd": winner["bid_data"]["price_usd"],
        },
    }})
```

## 4.4 Registering a function

Whatever you write must exist in the function registry under a
`function_id` *before* it's referenced by a `BidJob`. `AgentFunctions.add()`
(called automatically, lazily, the first time `FunctionCaller.call()` sees a
given `function_id`) does a `GET /functions/{function_id}` against
`FUNCTION_REGISTRY_URL` and raises `ValueError` if nothing is registered —
so an unregistered `bid_job_evaluator_id`/`bid_job_pqt_id` will fail the
*first* bid submission (for PQT) or fail silently in the background evaluate
thread (for the evaluator) rather than at job-creation time. Registering the
function itself (setting its `function_type`, `is_external` /
`external_function_url`, etc.) is done against the function registry
service directly — outside Orcade's own API surface.

---
[← Previous: APIs](03-apis.md) · [Back to index](README.md) · [Next: Delegate system →](05-delegate-system.md)
