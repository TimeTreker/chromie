# TaskGraph Concurrency Decision

## Decision status

Accepted and implemented across M11-M12 for eligible non-physical Agent
TaskGraph execution and host Skill Runtime scheduling.

The decision is:

> Use bounded process-local scheduling with explicit capability parallelism and
> exclusive-group policy. Preserve deterministic result order and keep physical
> motion sequential. Delegate cross-process robot exclusivity to Soridormi.

## Why bounded concurrency

Sequential execution was safe but unnecessarily delayed independent status,
planning, and speech work. Unbounded `asyncio.gather` would make cancellation,
resource conflicts, retries, traces, and failure propagation nondeterministic.
The shared `ResourceArbiter` provides one policy model for Agent and
Orchestrator without pretending to be a distributed scheduler.

## Implemented semantics

- `max_concurrency` bounds active work in one process.
- `can_run_parallel=false` prevents capability-level overlap.
- Matching non-empty `exclusive_group` values serialize conflicting work.
- Unrelated eligible groups may overlap.
- Dependency readiness is respected before dispatch.
- Returned node results and presentation traces are ordered deterministically,
  independent of completion timing.
- Cancellation is scoped to the owning graph or interaction.
- Fatal policy blocks or cancels the correct descendants and siblings.
- Timeouts, retries, and backoff use effective node/capability policy.
- A node is not dispatched more than once during preflight/fallback handling.

Agent parallel execution is enabled with:

```env
AGENT_ENABLE_PARALLEL_TASK_GRAPH_EXECUTION=1
AGENT_TASK_GRAPH_MAX_CONCURRENCY=4
```

Host Skill Runtime concurrency is bounded with:

```env
ORCH_SKILL_MAX_CONCURRENCY=4
```

Both are default-conservative and process-local.

## Physical work

Physical TaskGraph nodes remain sequential even when parallel graph execution
is enabled. They still require:

- guarded execution authorization;
- a valid graph-bound confirmation grant when required;
- an active covering safety monitor;
- a declared emergency fallback;
- explicit physical-execution enablement.

The host Skill Runtime also relies on Soridormi for embodied exclusivity,
cancellation, stop, and emergency behavior. An Agent arbiter and Orchestrator
arbiter cannot coordinate each other directly.

## Reliability requirements

The implementation and tests cover:

- independent eligible nodes overlapping under the configured bound;
- conflicting exclusive groups serializing;
- deterministic result order;
- timeout and retry behavior;
- graph-local cancellation;
- fatal failure propagation;
- default-off parity with the sequential executor;
- guarded non-physical concurrency;
- physical sequential behavior and proof retention.

Target microphone-to-MuJoCo interruption and supervised hardware evidence remain
acceptance activities described in [`ACCEPTANCE.md`](ACCEPTANCE.md); they are
not implied solely by unit/integration test coverage.

## Non-goals

The current scheduler is not:

- durable across process restart;
- distributed across hosts;
- a global lock service;
- a substitute for Soridormi safety policy;
- a background queue with delivery guarantees.

Those properties require a separate design and should not be inferred from the
current `ResourceArbiter`.
