[← Back to index](README.md)

# 4. Functions to write (invitation, PQT, evaluation, tie-breaker, post-award)

The voting system does not count votes itself. Every decision is delegated
to one of five hooks configured on the task:

| Hook | Field | Runs in | When | Required |
|---|---|---|---|---|
| Invitation creator | `voting_message_request_creator` | Submission service | Once, when the task starts | no |
| PQT | `voting_pqt` | Vote-intake service | Once per vote, inline | **yes** |
| Choice evaluation | `choice_evaluation` | Evaluator job | Once per task | **yes** |
| Tie-breaker | `tie_breaker` | Evaluator job | Only if choice evaluation returns more than one winner | no |
| Post-award | `post_awarding` | Evaluator job | Once per task, after the winners are final | **yes** |

Every hook receives a single JSON object as input and must return a single
JSON object as output. The services read only the keys documented below. A
malformed response either disqualifies the vote (PQT) or makes the evaluator
job exit with an error and no report (the other evaluation hooks). Nothing is
retried.

## 4.1 Two ways to plug in logic

A hook's [function spec](02-schema.md#25-function-spec) picks where its logic
lives:

- **`mode: "function"`**: a function in the **function registry**
  (`FUNCTIONS_REGISTRY_URL`), referenced by `function_id`. It runs through
  `AgentFunctions` (`submission/core/evaluators/agents_functions/`), which
  supports the same three execution modes as the bidding system:
  - **external** (`is_external=True`): a plain HTTP `POST` of the input JSON
    to `external_function_url`. The response's `"data"` key is returned, or
    the whole body if there is no `"data"` key.
  - **stateful** (`is_stateful=True`): deployed as a long-lived service on
    first use. The deployment is named `<function_name>-<SOCIAL_CHOICE_ID>`.
  - **stateless**: run once per call as a registry-managed job on
    `EXECUTOR_ID`, with the spec's `parameters`.

  The hook's output is read from the **`job_output_data`** key of the call
  result.
- **`mode: "dsl"`**: a workflow in the **DSL workflow registry**, referenced
  by `workflow_id`. The workflow's final output is the hook's output.

> **Which hooks support which mode today.** Only the invitation creator goes
> through the `mode` switch (`execute_functionality` in
> `submission/core/evaluators/__init__.py`). The PQT, choice evaluation,
> tie-breaker, and post-award hooks are run by `dsl_executor`'s
> `new_dsl_workflow_executor` against `WORKFLOWS_API_URL`, from the
> string fields `voting_pqt_dsl`, `choice_evaluation_dsl`, `tie_breaker_dsl`,
> and `post_awarding_dsl`. In practice those four hooks are **DSL workflows
> only** until the vote-intake and evaluator services move to the new schema
> ([§1.5 gap 1](01-concepts.md#15-current-implementation-gaps)).

### Authoring format: `AIOSv1PolicyRule`

Stateful and stateless registry functions, and the policy nodes inside a DSL
workflow, are all written the same way: as a class named exactly
`AIOSv1PolicyRule`. The runtime instantiates it from your code and calls
`eval()`.

```python
import logging


class AIOSv1PolicyRule:

    def __init__(self, rule_id, settings, parameters):
        """
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
        # ... decide, return a dict
```

| Piece | What it holds here |
|---|---|
| `settings` / `parameters` (constructor) | Static configuration stored with the function: thresholds, weights, allowed options. Read your tunables from these. Treat `__init__` as one-time setup, because a stateful deployment reuses the instance. |
| `input_data` (`eval`) | The input contract of the hook, as described below. Every hook's input is wrapped in a `user_input` key. |
| `parameters` (`eval`) | The function spec's `parameters`, for a stateless registry function. Empty otherwise. |
| `context` (`eval`) | Owned by the execution runtime. Nothing in the voting services depends on it. |
| return value | A JSON-serializable `dict`: the output contract of the hook. |

For an external function (`is_external=True`), the class contract does not
apply. Any HTTP service that accepts the input JSON and returns the output
JSON works.

### Common input

All hooks receive the task's configuration as dicts, wrapped in `user_input`:

| Key | Content | Hooks |
|---|---|---|
| `user_input.task` | `SocialTaskCoreData.to_dict()` | all |
| `user_input.subject_spec` | `SocialChoiceSubjectSpecInput.to_dict()` | all |
| `user_input.evaluation_spec` | `SocialChoiceEvaluationInput.to_dict()` | all except the invitation creator |

Each hook adds its own keys, as listed in its section.

## 4.2 Invitation creator

**Purpose:** build custom content for the invitation that goes out when the
task starts. For example: a personalised prompt, a deadline, or a ballot
schema.

**When it's called:** once, by `VotingTaskInitiator`, just before the
invitations are published. It is skipped if `voting_message_request_creator`
is `{}`.

**Input contract:**

```json
{
  "user_input": {
    "task": { "...": "SocialTaskCoreData.to_dict()" },
    "subject_spec": { "...": "SocialChoiceSubjectSpecInput.to_dict()" }
  }
}
```

**Output contract:** any JSON object. It is placed verbatim in the
invitation's `event_data.custom_data`
([§5.2](05-messaging.md#52-voting_invite-sent-when-a-task-starts)). The same
content goes to every recipient, because the hook runs once per task, not
once per recipient.

If the hook raises, no invitations are sent, the task stays `"scheduled"`,
and the scheduler retries it every 60 seconds
([§1.5 gap 8](01-concepts.md#15-current-implementation-gaps)).

**Reference implementation** (`AIOSv1PolicyRule`, stateless or stateful
registry function):

```python
import logging


class AIOSv1PolicyRule:

    def __init__(self, rule_id, settings, parameters):
        self.rule_id = rule_id
        self.settings = settings
        self.parameters = parameters

    def eval(self, parameters, input_data, context):
        logging.info("invite input: {}".format(input_data))

        spec = input_data["user_input"]["subject_spec"]
        return {
            "prompt": f"Please vote: {spec['topic_title']}",
            "ballot_schema": {"selected_option": list(spec["voting_options_map"].keys())},
            "vote_endpoint": self.settings.get("vote_endpoint", "http://voting-intake:8081/submit-vote"),
        }
```

**Alternative reference implementation** (external HTTP mode, Flask):

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.post("/")
def build_invite():
    spec = request.get_json()["user_input"]["subject_spec"]
    return jsonify({"data": {"job_output_data": {
        "prompt": f"Please vote: {spec['topic_title']}",
        "ballot_schema": {"selected_option": list(spec["voting_options_map"].keys())},
    }}})
```

The extra `job_output_data` level is needed because the submission service
reads the hook's output from that key ([§4.1](#41-two-ways-to-plug-in-logic)).

## 4.3 PQT (pre-qualification test)

**Purpose:** decide whether a single vote counts. For example: reject a
ballot that names an option that doesn't exist, a malformed ranking, or a
voter who fails an external eligibility check.

**When it's called:** inline, synchronously, inside `POST /submit-vote` (or
the NATS `vote.submit` handler), once per vote, after the initial checks in
[§3.4](03-apis.md#34-how-to-submit-a-vote) pass. The PQT is mandatory. A task
without one rejects every vote.

**Input contract:**

```json
{
  "user_input": {
    "task": { "...": "..." },
    "subject_spec": { "...": "..." },
    "evaluation_spec": { "...": "..." },
    "vote_data": { "...": "the vote's vote_data only" }
  }
}
```

The DSL executor is also given `addons: {"submitter_subject_id": "<voter>"}`.
`vote_data` does not carry the voter's ID, so read it from the addons if your
rule needs it.

**Output contract:**

| Key | Type | Required | Meaning |
|---|---|---|---|
| `qualified` | `boolean` | **yes** | Truthy: the vote is stored with `qualified = true` and counts toward evaluation. Falsy or missing: the vote is stored with `qualified = false`. It is ignored by evaluation, but it still uses up the voter's one vote. |
| *(anything else)* | any | no | Ignored. A `reason` field is useful for your own logs, but it is not returned to the voter. |

Unlike the bidding PQT, a negative verdict does **not** reject the request.
The voter gets `200` with `"qualified": false`.

**Example output:**

```json
{ "qualified": false, "reason": "option 'agent-translator-09' is not on the ballot" }
```

**Reference implementation** (`AIOSv1PolicyRule` policy node, option must be
on the ballot):

```python
import logging


class AIOSv1PolicyRule:

    def __init__(self, rule_id, settings, parameters):
        self.rule_id = rule_id
        self.settings = settings
        self.parameters = parameters

    def eval(self, parameters, input_data, context):
        logging.info("pqt input: {}".format(input_data))

        ui = input_data["user_input"]
        options = ui["subject_spec"]["voting_options_map"]
        choice = ui["vote_data"].get("selected_option")

        if choice not in options:
            return {"qualified": False, "reason": f"option {choice!r} is not on the ballot"}
        return {"qualified": True}
```

## 4.4 Choice evaluation

**Purpose:** given every qualified vote, decide the winner or winners. This is
where the social-choice rule lives: plurality, Borda, approval, Condorcet,
weighted voting, and so on.

**When it's called:** once per task, inside the evaluator job, after the
trigger condition in [§1.3](01-concepts.md#13-access-modes) is met.

**Input contract:**

```json
{
  "user_input": {
    "task": { "...": "..." },
    "subject_spec": { "...": "..." },
    "evaluation_spec": { "...": "..." },
    "votes": [ { "...": "Votes.to_dict()" }, "... qualified votes only" ]
  }
}
```

The DSL executor is also given `addons: {"social_task_id": "<id>"}`.

**Output contract:**

| Key | Type | Required | Meaning |
|---|---|---|---|
| `winner` | `string` | one of `winner` / `winners` | A single winner. Checked first. |
| `winners` | `array<string>` | one of `winner` / `winners` | One or more winners. More than one triggers the tie-breaker, if configured. |
| *(anything else)* | any | no | Kept in `report_json.dsl_outputs.choice_evaluation_dsl`. A good place for the tally. |

If neither key is present, the job raises and exits with no report, and the
task stays `"started"`.

Winners should be **option keys**. The result notification is published on a
NATS subject named after each winner ([§5.4](05-messaging.md#54-voting_result-sent-after-evaluation)),
so when the options are subject IDs, the winning subjects are notified
directly.

**Example output:**

```json
{
  "winner": "agent-translator-02",
  "tally": {"agent-translator-02": 2, "agent-translator-01": 1}
}
```

**Reference implementation** (plurality: most `selected_option` votes wins,
and every option tied for first is returned):

```python
import logging
from collections import Counter


class AIOSv1PolicyRule:

    def __init__(self, rule_id, settings, parameters):
        self.rule_id = rule_id
        self.settings = settings
        self.parameters = parameters

    def eval(self, parameters, input_data, context):
        logging.info("evaluation input: {}".format(input_data))

        votes = input_data["user_input"]["votes"]
        tally = Counter(v["vote_data"]["selected_option"] for v in votes)
        if not tally:
            return {"winners": [], "tally": {}}

        top = max(tally.values())
        winners = sorted(opt for opt, n in tally.items() if n == top)
        return {"winners": winners, "tally": dict(tally)}
```

An empty `winners` list passes through to post-award and the report, and no
one is notified. Decide whether your post-award hook should treat it as
"no decision".

**Ranked-ballot variant** (Borda count, with `vote_data` of the form
`{"ranking": ["agent-translator-02", "agent-translator-01", ...]}`):

```python
def eval(self, parameters, input_data, context):
    ui = input_data["user_input"]
    options = list(ui["subject_spec"]["voting_options_map"].keys())
    n = len(options)
    scores = {opt: 0 for opt in options}

    for v in ui["votes"]:
        for position, opt in enumerate(v["vote_data"]["ranking"]):
            if opt in scores:
                scores[opt] += n - 1 - position

    top = max(scores.values())
    return {"winners": [o for o, s in scores.items() if s == top], "scores": scores}
```

## 4.5 Tie-breaker

**Purpose:** reduce several tied winners to fewer, usually one.

**When it's called:** inside the evaluator job, only if choice evaluation
returned more than one winner **and** a tie-breaker is configured. If no
tie-breaker is configured, all tied winners are final.

**Input contract:** the choice-evaluation input, plus the tied winners:

```json
{
  "user_input": {
    "task": { "...": "..." },
    "subject_spec": { "...": "..." },
    "evaluation_spec": { "...": "..." },
    "votes": [ "..." ],
    "winners": ["agent-translator-01", "agent-translator-02"]
  }
}
```

**Output contract:** the same as choice evaluation. Return `winner` or
`winners`. The result replaces the winner list and is not checked again, so
returning more than one winner leaves the tie in place.

**Reference implementation** (earliest vote for any tied option wins):

```python
def eval(self, parameters, input_data, context):
    ui = input_data["user_input"]
    tied = set(ui["winners"])
    ballots = sorted(
        (v for v in ui["votes"] if v["vote_data"].get("selected_option") in tied),
        key=lambda v: v["submission_time"],
    )
    return {"winner": ballots[0]["vote_data"]["selected_option"], "rule": "earliest_vote"}
```

## 4.6 Post-award

**Purpose:** turn the decision into action and describe it for the winners.
For example: assign work, record an agreement, or set a start time.

**When it's called:** once per task, inside the evaluator job, after the
winners are final. It always runs, even when the winner list is empty.

**Input contract:** the choice-evaluation input, plus the final winners:

```json
{
  "user_input": {
    "task": { "...": "..." },
    "subject_spec": { "...": "..." },
    "evaluation_spec": { "...": "..." },
    "votes": [ "..." ],
    "winners": ["agent-translator-02"]
  }
}
```

**Output contract:** any JSON object. It becomes `post_award_payload`, which
is stored in `report_json` and sent to every winner in the `voting_result`
notification ([§5.4](05-messaging.md#54-voting_result-sent-after-evaluation)).
Put everything the winners need to act on here.

**Example output:**

```json
{
  "assigned_to": "agent-translator-02",
  "start_by": "2026-10-23T09:00:00Z",
  "document_url": "https://storage.example.com/docs/q4-handbook.pdf"
}
```

**Reference implementation:**

```python
def eval(self, parameters, input_data, context):
    ui = input_data["user_input"]
    winners = ui["winners"]
    if not winners:
        return {"decision": "none", "reason": "no qualified votes"}
    return {
        "decision": "assigned",
        "assigned_to": winners[0],
        "goal": ui["task"].get("goal_data", {}),
    }
```

## 4.7 Registering hooks

Every `function_id` and `workflow_id` must exist in its registry **before**
the hook runs. Nothing is checked at task creation, so a missing hook fails
late:

| Hook | Failure when the ID is not registered |
|---|---|
| Invitation creator | `AgentFunctions.add()` raises `ValueError`. The task stays `"scheduled"` and is retried every minute. |
| PQT | The workflow call raises, and every vote is stored with `qualified = false`. |
| Choice evaluation, tie-breaker, post-award | The evaluator job exits with an error. There is no report, and the task stays `"started"`. |

Registering a function (its `function_type`, `is_external`,
`external_function_url`, and so on) or a DSL workflow is done against the
registry service directly, outside the voting system's API.

Use [`POST /parse-social-choice-task`](03-apis.md#33-how-to-validate-a-task-without-creating-it)
to confirm the stored field names. Then run each hook against its registry
with a sample `user_input` before you create a real task.

---
[← Previous: APIs](03-apis.md) · [Back to index](README.md) · [Next: Messaging →](05-messaging.md)
