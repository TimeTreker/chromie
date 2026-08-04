# Grounded External Information

## Purpose

Use this passive method for the information branch of an `acquire_and_deliver_resource` Goal: weather, restaurant or place recommendations, current facts, news, how-to research, or other externally verified information. It helps an Agent preserve authoritative Goal bindings, choose between exact verified-memory retrieval and a fresh read, distinguish failure stages, and produce evidence-grounded speech.

This Agent Skill does not resolve references by itself, call a provider, register a Capability, authorize execution, or define a Host Workflow. Goal Association remains responsible for semantic binding and reference resolution. Plans still reference registered `capability_id` values, and trusted execution evidence remains the only source of external facts.

## Method

1. Establish the current Goal and all material bindings before retrieval.
2. Treat memory indexes as metadata that a result may be retrievable, never as answer evidence.
3. Reuse a result only through the verified-memory Capability when tool identity, every material argument, and freshness match the current Goal.
4. Otherwise select the most exact fresh read Capability. Prefer a specialized contract such as weather when its semantic scope fits; use a general external-information provider for grounded web facts, recommendations, places, restaurants, news, or how-to research. Clarify an unresolved material binding or report the need unavailable rather than substituting a nearby topic.
5. Before evidence exists, speech may acknowledge the pending read but must not claim a fact, measurement, conclusion, or completion.
6. Interpret success and failure from trusted execution evidence, distinguishing binding, capability, retrieval, provider/network, and result-interpretation stages.
7. Answer with only relevant supported facts, calibrated uncertainty, and natural wording for the user.

## Boundaries

- Old evidence cannot resolve a current pronoun or overwrite a current Goal binding.
- A stale or mismatched memory entry is not a partial answer; it requires a fresh read or an honest limitation.
- The Goal is provider-neutral. Provider selection belongs to planning, and provider adaptation belongs inside the executable Capability adapter.
- Evidence retrieval, evaluation, and natural spoken explanation are stages of one information-resource responsibility, not separate user Goals.
- No fixed acknowledgement wording or length is imposed by this Skill.
- Package availability does not grant execution authority.
