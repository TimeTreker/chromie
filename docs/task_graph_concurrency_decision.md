# TaskGraph concurrency and shared scheduling decision

Status: accepted with amendments  
Date: June 13, 2026

## Decision

Chromie will evolve its existing Capability Registry, TaskGraph executors, and
Skill Runtime. It will not add an independent `CapabilityDAGRunner` or a
distributed workflow/queue dependency.

TaskGraph and Skill Runtime remain separate public interfaces:

- TaskGraph schedules dependency-aware capability nodes.
- Skill Runtime schedules speech and named skill requests.

They will converge on one scheduling and reliability contract for concurrency
limits, exclusive resources, timeouts, retries, cancellation, result ordering,
and traces. Shared internals must not weaken either interface's validation or
safety boundary.

## Amendments to the recommendation

### Resource locks are runtime-scoped

Tasks, futures, dependency results, activated fallbacks, and cancellation state
must be local to one execution. Resource arbitration is deliberately not local.

An exclusive group such as `soridormi.robot_motion` or `chromie.audio` must
serialize work across concurrent executions hosted by the same runtime.
Graph-local locks would allow separate requests in that runtime to operate the
same physical or audio resource simultaneously.

The implementation should therefore separate:

- `GraphRunState`: execution-local mutable state;
- `ResourceArbiter`: execution-host-scoped semaphores and exclusive-group
  locks.

The arbiter must be in-process and bounded. This decision adds no broker,
distributed lock, workflow engine, or queue.

TaskGraph currently runs in the Agent process while Skill Runtime runs in the
host Orchestrator. They therefore use separate arbiter instances that implement
the same contract. Cross-process exclusivity for robot work remains enforced by
the Soridormi MCP/provider runtime, which owns the physical resource and rejects
or serializes conflicting active work. Chromie must not pretend that an
in-memory Agent lock protects the Orchestrator, or vice versa.

### Sequential fallback must not replay side effects

The parallel scheduler will be default-off and can immediately fall back to the
current sequential executor before any node is invoked. Once execution starts,
Chromie must not replay the graph sequentially because doing so could duplicate
planning writes, speech, or physical effects.

After dispatch begins, failures use the graph's existing timeout, retry,
failure-policy, stop, and emergency behavior. Operational rollback means
disabling the feature flag for later executions, not replaying an in-flight
graph.

## Baseline code assessment

At decision time, Chromie already had the necessary foundations:

- `ExecutionPolicy` declares `can_run_parallel`, `exclusive_group`,
  `timeout_s`, idempotency, and side-effect behavior.
- TaskGraph validation enforces manifest, reference, confirmation, monitor,
  fallback, and physical-motion rules.
- async read-only, planning, and guarded executors already preserve the MCP
  invocation and safety boundaries.
- Skill Runtime already supports parallel batches, exclusive groups, timeouts,
  cancellation, and traces.

The baseline implementations did not yet share scheduling machinery:

- ready TaskGraph nodes execute one at a time;
- TaskGraph execution does not consistently apply capability concurrency
  policy, timeout, retry backoff, or default failure policy;
- Skill Runtime has unbounded parallel batches;
- Skill Runtime locks and active-request state are runtime-instance mutable
  state rather than an explicit execution-state/resource-arbitration split;
- deterministic completion ordering under true concurrency is not specified.

These are reasons to consolidate policy and scheduling primitives, not reasons
to add another runner.

## Scheduling contract

The common contract will enforce:

1. Validate the complete request or graph before dispatch.
2. Assign Skill Runtime items stable input order and TaskGraph nodes stable
   node-ID order.
3. Dispatch only dependency-ready work.
4. Bound active work with a configurable semaphore.
5. Serialize items whose capability has `can_run_parallel=false`.
6. Serialize items sharing a non-null `exclusive_group`.
7. Apply the effective timeout from the request/node and capability policy.
8. Apply bounded retry and backoff only where policy permits it.
9. Propagate cancellation to active work and await required cleanup.
10. Return results and normalized trace records in stable order independent of
    completion timing.
11. Keep physical motion sequential by default, even when graph concurrency is
    enabled.
12. Preserve confirmation, monitor, stop, emergency, manifest, schema, and
    invocation-policy checks exactly as independent gates.

Trace timestamps may reflect real concurrent completion. Stable result order
must not falsify causality; trace events should carry a monotonic sequence
number and stable item order so consumers can choose execution or presentation
order explicitly.

## C0 reliability semantics

- Read/planning TaskGraph timeout uses `TaskNode.timeout_s` when present,
  otherwise the capability execution timeout.
- Read/planning retries use the node retry policy, default to one attempt, and
  retry only `failed_retryable` outcomes. Capability-default retry/failure
  consolidation remains C3.
- A terminal read/planning failure blocks dependent nodes. These executors do
  not activate side-effecting fallback nodes.
- Skill Runtime timeout uses the request timeout when present, otherwise the
  registered skill timeout. Skill retries are not currently part of its
  contract.
- Skill Runtime cancellation propagates to active cancellable/interruptible
  work and awaits provider cleanup.
- Guarded TaskGraph confirmation, monitor, stop, emergency, and cancellation
  semantics remain unchanged by C0-C2.

## Delivery plan

### C0 - Freeze semantics and characterization tests

Status: complete locally.

- Document effective timeout, retry, failure, and cancellation precedence.
- Add tests for current sequential traces and safety behavior.
- Preserve Pydantic and manifest validation for concurrency declarations.
- Define stable node ordering and graph terminal-status rules.

Gate: existing sequential behavior and safety tests remain unchanged.

### C1 - Extract shared scheduling primitives

Status: complete locally for the in-process arbiter and Skill Runtime
integration.

- Add execution-local TaskGraph run state.
- Add an execution-host-scoped in-process resource arbiter, instantiated
  separately by Agent TaskGraph and host Skill Runtime.
- Add bounded dispatch and deterministic result ordering around the shared
  arbiter; retain timeout and retry/backoff behavior in each execution
  interface until C3 consolidation.
- Adapt both execution hosts to the common arbiter contract without changing
  their public contracts.
- Remove request-ID collision risk by keying active work by execution identity
  plus request ID.

Gate: TaskGraph and Skill Runtime tests prove bounded concurrency,
same-host cross-execution exclusive groups, active-key collision isolation, and
deterministic returned ordering.

### C2 - Parallel read-only and planning TaskGraphs

Status: complete locally behind default-off flags.

- Add `AGENT_ENABLE_PARALLEL_TASK_GRAPH_EXECUTION=0`.
- Add `AGENT_TASK_GRAPH_MAX_CONCURRENCY` with a conservative default.
- Run independent eligible read-only and planning nodes concurrently.
- Respect dependencies, `can_run_parallel`, exclusive groups, and policy
  timeouts.
- Select the current sequential executor before dispatch whenever the flag is
  disabled. Invalid scheduler configuration fails startup before dispatch.

Gate: timing tests prove overlap; stress tests prove the bound; repeated runs
produce identical result ordering; concurrent graphs do not share run state.

### C3 - Reliability and cancellation parity

Status: complete locally.

- Apply node and capability retry/backoff consistently.
- Preserve graph failure policies and blocked-node propagation.
- Cancel sibling work only when the selected failure policy requires graph
  termination.
- Ensure cancellation waits for provider/invoker cleanup.
- Retain partial traces without replaying invoked nodes.

Gate: timeout, retry, partial failure, cancellation, and fallback tests pass for
both sequential and parallel modes.

### C4 - Guarded execution integration

Status: complete locally and verified against the Soridormi runtime in MuJoCo.

- Allow concurrency only for guarded nodes proven non-physical and policy-safe.
- Keep confirmation nodes, monitors, safety controls, and physical motion on
  the conservative sequential path initially.
- Require the Soridormi provider/runtime to keep `soridormi.robot_motion`
  globally exclusive across Agent TaskGraph and host Skill Runtime callers.
- Re-run supervised cancellation and emergency-fallback acceptance in MuJoCo.

Gate: no parallel path can bypass confirmation, active-monitor proof, stop, or
emergency fallback; physical work remains sequential by default.

### C5 - Rollout and consolidation

Status: complete for the default-off development and simulation rollout.

- Expose scheduler mode, configured limit, queue delay, and active count in
  health/trace diagnostics.
- Compare sequential and parallel outcomes in CI fixtures.
- Enable parallel read/planning execution in development, then simulation.
- Retain the sequential implementation as an immediate deployment rollback
  until acceptance evidence is stable.
- Remove duplicated scheduling logic only after TaskGraph and Skill Runtime
  pass the same conformance suite.

Gate: measured latency improves for independent reads/plans without changing
results, safety outcomes, or cancellation cleanup.

## Completion evidence

On June 13, 2026:

- 122 current unittest cases and 20 legacy Agent tests passed;
- focused guarded execution, Soridormi acceptance, and MCP invoker suites
  passed;
- the live Soridormi capability probe advertised all 12 expected tools;
- the rebuilt Agent completed a five-second runtime-plan cancellation with
  parallel TaskGraph scheduling enabled;
- the guarded trace retained deterministic ordering, marked the physical node
  cancelled, and completed the declared emergency fallback on its first
  attempt;
- Soridormi reported `active_task=null` and `emergency_stop=true` after
  cancellation.

The feature remains disabled by default. Deployment rollback remains the
pre-dispatch feature flag; in-flight graphs are never replayed.

## Required test matrix

- independent nodes overlap;
- dependencies never overlap incorrectly;
- concurrency never exceeds the configured bound;
- `can_run_parallel=false` serializes execution;
- matching exclusive groups serialize across concurrent executions in each
  execution host;
- provider integration rejects or serializes conflicting robot work arriving
  from Agent TaskGraph and host Skill Runtime processes;
- unrelated exclusive groups may overlap;
- result and presentation-trace order is deterministic;
- timeout, retry count, and backoff follow effective policy;
- one graph's cancellation cannot cancel another graph;
- fatal policy cancels or blocks the correct siblings and descendants;
- feature-off behavior matches the current sequential executor;
- pre-dispatch fallback invokes each node at most once;
- physical motion remains sequential and retains confirmation/monitor proofs;
- interruption retains stop and emergency behavior in MuJoCo.

## Non-goals

- distributed execution or persistence;
- a new DAG schema or planner;
- replacing MCP invocation policy;
- increasing physical-motion parallelism;
- automatic replay after partial execution;
- merging TaskGraph and Skill Runtime into one public API.
