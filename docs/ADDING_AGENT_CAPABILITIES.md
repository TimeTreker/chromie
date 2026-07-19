# Adding Agent and Tool Capabilities

This guide explains how to add a new Chromie-side Agent or read-only tool so the
fast Router, downstream Agents, Orchestrator, and logs all agree on what the
robot can do.

Chromie should not rely on hidden code paths that only one Agent knows about. If
an Agent can answer or perform a user request, that capability must be exposed in
the Agent capability catalog so the Router can ground natural language against a
real affordance.

## Mental model

Use this split for new capabilities:

```text
User request
  -> Router sees catalog affordance and chooses route/routes plus fast_speech
  -> Agent receives the route and metadata/proposal
  -> Agent/tool performs read-only lookup or creates a proposal
  -> SkillRuntime/Soridormi validate physical work when applicable
  -> Speaker reports grounded result or asks for clarification
```

The Router may generate a short process acknowledgement such as “好的，我查一下重庆今天的天气。” It must not invent the final answer. The Agent/tool owns the grounded result.

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
   - Use `agent/app/agents/tool.py` for small read-only tools such as weather.
   - Use a dedicated Agent class when the capability has its own state machine,
     planner, long-running workflow, or domain-specific adjudication.

2. **Expose the capability in the registry.**
   - Add an `AgentManifest` and `ToolCapability` in
     `agent/app/capabilities/local.py`, or provide an external manifest through
     `AGENT_CAPABILITY_MANIFESTS`.
   - Give it a stable globally unique name such as `chromie.weather.lookup`.
   - Include a semantic description, not phrase rules.
   - Include an `input_schema` with units, enums, ranges, required fields, and
     user-facing parameter descriptions.

3. **Set routing metadata.**
   - `effects` should describe what the capability does, for example
     `read_only`, `external_read`, or `weather_lookup`.
   - `safety_class` should be `safe_read` for read-only lookups.
   - Put common, safe, frequently requested tools in the `common` prompt tier by
     setting `llm_hints.prompt_tier = "common"` or adding the capability to
     `capabilities/prompt_tiers.json`.
   - Add `llm_hints.tool_name`, `llm_hints.router_contract`, and any compact
     guidance that helps the Router choose the correct route without examples.

4. **Connect execution in the owning Agent.**
   - The Agent should detect its route using route/intent/metadata, then call the
     actual client/service.
   - For read-only tools, failures should be explicit: disabled, missing
     location, lookup not found, timeout, or provider error.
   - The Agent should produce a grounded spoken result only after the data source
     returns.

5. **Make the Router prompt and review stages aware of the route contract.**
   - Main quick Router prompts can mention the general tool family.
   - Intent review and repair prompts must use the same route/tool contract if
     they can override or repair quick routing.
   - Do not make Orchestrator template the user-facing acknowledgement when the
     Router can supply `fast_speech`.

6. **Add observability.**
   - Router logs should show the capability in `tool_like_ability_ids` or a more
     specific diagnostic field.
   - Agent logs should show start, parameter extraction, client lookup, success,
     and failure reasons.

7. **Add tests.**
   - Registry/catalog test: the capability is visible in the expected prompt
     tier and has the expected route.
   - Search/routing test: representative user requests match the capability.
   - Agent test: metadata and LLM-extracted parameters are handled correctly.
   - Prompt/review test: review stages preserve the same route contract.

8. **Audit the authoritative contract.**
   - Run `python -m tools.chromie_cli capability check` for static validation.
   - When the provider is available, run
     `python -m tools.chromie_cli capability check --live` and review missing,
     extra, and schema-drift findings.
   - Do not treat a provider's extra advertised tools as registered Chromie
     abilities. The manifest and live provider must be intentionally aligned
     before those tools can enter planning or execution.

## Weather lookup example

The weather lookup capability is registered as:

```text
capability_id: chromie.weather.lookup
agent_id: chromie.weather
route: tool
effects: read_only, external_read, weather_lookup
safety_class: safe_read
prompt_tier: common
```

Its schema exposes `location`, `date`, and `units`. The Router should treat
current or upcoming weather questions as `route=tool` / `intent=weather_query`
when this capability is visible. The Router may say it will check the requested
weather, but only the Weather Tool Agent may report the weather result after the
lookup returns.

## Anti-patterns

Do not add a tool only as hidden Agent code. The Router will not reliably choose
it if it is absent from the catalog.

Do not add large phrase tables such as “重庆天气 -> weather”. Use semantic
capability descriptions and schemas instead.

Do not let a read-only tool path fall back to ordinary conversation that says “I
cannot access realtime data” when the catalog advertises a working tool. If the
tool is disabled, the Agent should say it is disabled.

Do not let Router `fast_speech` claim final results, permanent memory writes, or
physical completion. It is only a short acknowledgement before downstream work
finishes.
