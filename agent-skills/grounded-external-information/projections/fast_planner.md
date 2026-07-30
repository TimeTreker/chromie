## Grounded external information method — Fast Planner

Plan only after authoritative Goal bindings are available. A verified-memory index contains no answer facts. Choose `chromie.memory.retrieve_verified_tool_result` only when an indexed completed result has the same original tool identity, every material argument exactly matches the current Goal, and its freshness is adequate for the request. Execute that retrieval explicitly; never answer directly from the index.

If any binding differs, freshness is insufficient, or no matching result exists, choose an appropriate fresh read Capability. If a material binding is unresolved, clarify. If no registered Capability can satisfy the scope, report unavailable or escalate rather than narrowing the Goal. For a pending or recoverable read, resume or retry its exact bound Capability and arguments. Keep all step arguments equal to canonical bindings and make ordering/concurrency explicit.
