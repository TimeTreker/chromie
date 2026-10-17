# Adding Agent and Tool Capabilities

This guide explains how to add a new Chromie-side Agent or read-only tool so
catalog projection, Goal Association, canonical planning, the Trusted Capability
Runtime, and evidence all agree on what Chromie can do.

Chromie should not rely on hidden code paths that only one Agent knows about. If
an Agent can perform a registered read or effect, that Capability must be exposed
in the catalog so the model-owned planner can select an exact real affordance.
Catalog presence does not itself decide user meaning, authorize execution, or
prove availability.

## Mental model

Use this split for new capabilities:

```text
User request
  -> Cognitive Gateway admits an immutable UserTurnEnvelope
  -> User Meaning Interpretation states the Responsibility (WHAT)
  -> Goal Association resolves canonical Goal continuity
  -> the Planner selects an exact registered Capability
  -> Value Judgment reviews it when the Capability is value-reviewed
  -> Trusted Capability Runtime validates and invokes the owning Provider
  -> exact result Evidence is reconciled to the source Goal and Plan
  -> the Planner re-enters with trusted Evidence and states the communication Need
  -> Social Cognition authors the grounded Communicative Activity
```

Social Cognition owns every user-facing Communicative Activity, including any
receipt spoken before canonical Goal identity exists. Such speech is grounded only
in the admitted turn and current truth stage; it must not claim Capability
selection, execution, result Evidence, or Goal completion. The Host transports only
exact validated Activities and does not author a generic acknowledgement. Every
cognitive re-entry follows the still-needed-delta rule: an equivalent audible or
pending act is referenced by exact speech-event identity rather than repeated, and
text equality is never de-duplication authority.

An **Agent Skill** is a different object. It is passive reusable task
knowledge selected by an Agent to help generate a Plan. Adding an Agent
Skill does not add an executable capability, provider, permission, or route. See
[Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md).

## Resource-provider capabilities

For a capability that acquires and delivers a resource, declare semantic scope rather than relying on provider names or topic keywords. Physical and information providers are peers. A complete contract should state `responsibility_type=acquire_and_deliver_resource`, supported `resource_kinds`, acquisition semantics, delivery semantics, and complete-outcome evidence. Partial primitives must not claim the full responsibility. See [Resource Acquisition and Delivery](RESOURCE_ACQUISITION_AND_DELIVERY.md).

## One authoritative capability contract

Keep contributor guidance separate from execution authority. A capability may have
additional prose, examples, or an external ecosystem description beside it, but
Chromie runtime behavior must continue to come from the existing typed manifest or
registered provider schema. Descriptive files do not register a provider, grant a
tool permission, authorize physical motion, or replace runtime validation.

Do not introduce package scanning, automatic script loading, or another capability
registry unless a concrete interoperability requirement cannot be met through the
current manifest and MCP/provider path. Any future adoption must be incremental,
optional, and reviewed as an authority-boundary change rather than a convenience
feature.

## Registration checklist

1. **Create or select the Agent implementation.**
   - Small read-only tools such as weather execute in
     `agent/app/local_tool_execution.py` and are declared in
     `agent/app/capabilities/local.py`.
   - Use a dedicated Agent class when the capability has its own state machine,
     long-running workflow, or domain-specific result interpretation. It must not
     become a second canonical planner.

2. **Expose the capability in the registry.**
   - Add an `AgentManifest` and `ToolCapability` in
     `agent/app/capabilities/local.py`. An external manifest supplied through
     `AGENT_CAPABILITY_MANIFESTS` adds catalog entries for a remote provider
     such as Soridormi (MCP transport); it cannot make a Chromie-side local tool
     executable, because local execution needs a trusted handler (see "Bind
     execution to the owning Provider").
   - Give it a stable globally unique name such as `chromie.weather.lookup`.
   - Include a semantic description, not phrase rules.
   - Include an `input_schema` with units, enums, ranges, required fields, and
     user-facing parameter descriptions.
   - When a provider argument can copy one canonical Goal binding unchanged under a
     different field name, `x-chromie-entity-type` may declare that exact read-only
     projection. When provider arguments require semantic transformation of a human
     scope, declare `llm_hints.argument_realization` instead. Planner owns that HOW
     mapping after capability selection and records `semantic_realization` provenance;
     UMI/GA do not pre-shape Goal semantics to the provider schema.

3. **Set routing metadata.**
   - `effects` should describe what the capability does, for example
     `read_only`, `external_read`, or `weather_lookup`.
   - `safety_class` should be `safe_read` for read-only lookups.
   - The Trusted Capability Runtime registers a local tool only when all of
     these hold (`orchestrator/runtime/agent_tool_provider.py`
     `local_agent_tool_definitions`): transport `local_python`,
     `llm_hints.interaction_executable = true`, `safety_class = "safe_read"`,
     `execution.side_effect_free = true`, and no required confirmation. A tool
     that misses any of them stays in the catalog but is silently not
     registered for execution, and `LocalToolExecutor` refuses it.
   - Put common, safe, frequently requested tools in the `common` prompt tier by
     setting `llm_hints.prompt_tier = "common"` or adding the capability to
     `capabilities/prompt_tiers.json`.
   - Add `llm_hints.tool_name`, `llm_hints.semantic_type`,
     `llm_hints.semantic_scope`, `llm_hints.when_to_use`, and any compact
     guidance that helps model-owned interpretation and planning understand the
     Capability without phrase examples. Add `pre_execution_speech_guidance` only when the Capability needs
     compact pre-result truth constraints for a Social Cognition Communicative Activity.

4. **Bind execution to the owning Provider.**
   - A local tool runs only through a handler registered by exact capability
     ID in `LocalToolExecutor._handlers` (`agent/app/local_tool_execution.py`);
     without one the call returns `provider_not_bound`.
   - The execution adapter must require an exact plan-selected `capability_id`
     and schema-valid arguments; it must not infer a call from route, intent, or
     user-text phrases.
   - For read-only tools, failures should be explicit: disabled, missing
     arguments, lookup not found, timeout, schema failure, or provider error.
   - Return structured result evidence. Do not compose final user speech inside
     the Provider adapter.

5. **Expose the Capability to model-owned planning.**
   - Catalog projection may present the compact semantic description and schema
     to User Meaning Interpretation and the Planner.
   - User Meaning Interpretation owns what the user means and Goal Association
     owns continuity; the Planner
     owns exact Capability selection and complete Goal coverage.
   - Review/repair stages may reject malformed or out-of-envelope proposals, but
     deterministic code must not substitute another Capability or invent user
     meaning.

6. **Add observability.**
   - Catalog/interpretation traces should show which bounded candidate set was
     supplied without treating retrieval rank as semantic choice.
   - Plan, request, Provider, and result traces should preserve exact Capability,
     schema, Goal, Plan, request, and evidence identities plus failure reasons.

7. **Add tests.**
   - Registry/catalog test: the Capability is visible in the expected prompt
     tier with a closed schema and correct safety/effect metadata.
   - Model-contract scenario: representative paraphrases produce the correct
     Goal and exact plan-selected Capability without phrase-specific Host rules.
   - Provider test: exact arguments, timeout, schema validation, and structured
     result/failure evidence are handled correctly.
   - End-to-end contract test: no result is spoken before exact request/result
     reconciliation, and unsupported or partial work fails honestly.

8. **Audit the authoritative contract.**
   - For a Chromie-side local tool, the registry, provider, and execution tests
     listed under "Add tests" are the audit (for example `tests/test_agent_tool_provider.py`
     and `tests/test_local_tool_execution.py`).
     `python -m tools.chromie_cli capability check` validates one JSON
     manifest (`capabilities/soridormi.json` by default) and does not load or
     check local tools.
   - For an external provider manifest, run
     `python -m tools.chromie_cli capability check` for static validation and,
     when the provider is available,
     `python -m tools.chromie_cli capability check --live`, then review
     missing, extra, and schema-drift findings.
   - Do not treat a provider's extra advertised tools as registered Chromie
     abilities. The manifest and live provider must be intentionally aligned
     before those tools can enter planning or execution.

## Agent Skill boundary

Do not use this capability-registration process to create a second executable
path from `SKILL.md`. A weather Agent Skill may teach Agents how to decide
between verified memory, a fresh lookup, clarification, and grounded failure
speech. The executable weather call still must be registered here as
`chromie.weather.lookup` and pass the same trusted runtime boundary.

## Weather lookup example

The weather lookup capability is registered as:

```text
capability_id: chromie.weather.lookup
agent_id: chromie.weather
effects: read_only, external_read, weather_lookup
semantic_type: weather_lookup
safety_class: safe_read
prompt_tier: common
```

Its schema exposes `location` (required), optional `location_context`,
`date` (`today` or `tomorrow`), `period` (`day`, `morning`, `afternoon`,
`evening`, or `night`), and `units`. Its `llm_hints` also set
`interaction_executable: true`, and its execution policy sets
`side_effect_free: true`. Goal Association preserves
the weather Goal and its continuity; the Planner may
select `chromie.weather.lookup` only when the catalog and Goal require it. The
Provider returns structured weather evidence, and only the evidence-bound
Social Cognition act may report the result after exact reconciliation.

## Anti-patterns

Do not add a tool only as hidden Agent code. The Planner cannot
select or prove a Capability that is absent from the catalog.

Do not add large phrase tables such as “重庆天气 -> weather”. Use semantic
capability descriptions and schemas instead.

Do not let a read-only tool path fall back to ordinary conversation that says “I
cannot access realtime data” when the catalog advertises a working tool. If the
Capability is disabled or fails, return a structured grounded failure so the
model-owned response boundary can report it honestly.

User Meaning Interpretation has no speech contract. Any pre-Goal-binding speech is a
Social Cognition Communicative Activity and must not claim a selected Capability, final
result, permanent memory write, physical completion, or any truth stage that Runtime /
Evidence has not established.
