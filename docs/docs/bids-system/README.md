# Bidding System (Orcade)

Orcade is a bidding orchestration service. A **creator** publishes a **bid
job** to a fixed set of eligible **subjects** (agents), each subject submits
a **bid**, and once every eligible subject has bid, a pluggable **evaluator
function** picks a winner. All communication with subjects happens through
an external **delegate system**, and all decision logic (qualification
checks, evaluation) is delegated to functions hosted in an external
**function registry** — Orcade itself only orchestrates state and timing.

Source of truth for everything in this documentation set:

| File | Responsibility |
|---|---|
| `core/schema.py` | `BidJob`, `Bid`, `BidTaskResult` dataclasses |
| `core/db.py` | MongoDB persistence for the three collections above |
| `core/bidding.py` | `BiddingService` — the orchestration logic |
| `core/apis.py` | Flask REST API (`app`, mounted via `main.py` / `run_server()`) |
| `core/functions.py` | `FunctionCaller` — thin wrapper for invoking PQT/evaluator functions |
| `core/agents_functions/` | Low-level client for the function registry (`AgentFunctions`, `FunctionsRegistryClient`, `FunctionCaller`) |
| `core/subject_task.py` | `SubjectTask` — client for the delegate system |

## Contents

1. [Concepts](01-concepts.md) — actors, lifecycle, closed vs. open bidding modes
2. [Schema](02-schema.md) — `BidJob`, `Bid`, `BidTaskResult` field references and sample documents
3. [APIs](03-apis.md) — full REST reference: creating jobs, submitting bids, querying
4. [Functions to write](04-functions.md) — PQT and evaluator function contracts, with reference implementations
5. [Delegate system](05-delegate-system.md) — how job/winner data is delivered to a subject agent
6. [Using the client library](06-using-client-library.md) — the standalone Python client: dataclasses, functions, poller, errors
7. [Using the client in the agent SDK](07-using-client-in-agent-sdk.md) — wiring the client into an agents-sdk agent, with a worked example
