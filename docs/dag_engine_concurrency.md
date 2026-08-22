# DAGEngine Concurrency

Status: current deterministic execution policy.

DAGEngine may dispatch multiple ready WorkDAG nodes concurrently only when all relevant Capability execution contracts permit it.

Concurrency is a mechanical property of an already Planner-authored WorkDAG. DAGEngine does not decide that two semantically unrelated activities "should" be parallel; it evaluates whether committed ready nodes may safely overlap.

## Mechanical gates

A node can enter a parallel wave only when:

- all committed dependencies are satisfied;
- it is not blocked by a failed dependency or dormant fallback edge;
- the Capability declares parallel execution support where required;
- exclusive-resource groups do not conflict;
- guarded physical execution satisfies confirmation and safety-monitor proof;
- cancellation has not invalidated the DAG/node.

If these conditions are not met, DAGEngine serializes or blocks mechanically. It does not change Work meaning to create concurrency.

## Failure

Parallel sibling failure follows the failure policy already authored in the WorkDAG or declared by the Capability's deterministic default contract. DAGEngine may cancel siblings when that policy requires it.

DAGEngine never responds to failure by inventing a replacement node, alternative Capability, or residual plan. It records terminal facts; Planner decides any new HOW after Evidence re-entry.

## Resource arbitration

The current implementation uses process-local resource arbitration. It is not a distributed scheduler and does not claim provider-global ownership. Provider-local controllers remain authoritative for their own physical/runtime resources.
