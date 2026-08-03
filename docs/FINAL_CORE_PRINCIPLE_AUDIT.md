# Final Core-Principle Audit

Status: implementation audit; non-authoritative evidence record
Initial date: 2026-07-30
Follow-up date: 2026-08-03
Current authorities: `config/documentation_authority.json`

## Scope

This audit was performed after completion of every named implementation Issue in
the project handoff. It reviewed:

- semantic-authority ownership;
- Agent Skill, Plan, Capability, and Provider separation;
- Host validation versus Host-authored intelligence;
- Chromie/Soridormi brain-body boundaries;
- Benchmark purity;
- current serialization and evidence terminology;
- current documentation authority and architecture consistency.

## Governing principles

> Thinking belongs to the LLM.

> Benchmark evaluates intelligence; it must not implement intelligence.

> Agent Skills teach methods; Capabilities execute.

> Chromie is backend-agnostic; Soridormi owns physical feasibility and safety.

## Violations found and corrected

### Host semantic delegation

A default-on Host `DeepThinkingDelegationPolicy` still routed ordinary turns
using confidence thresholds, intent strings, user-state labels, and physical
term lists. It was removed. Fast-versus-Deep planning is now owned by the
LLM-driven cognitive path and its typed contracts.

### Re-enableable phrase agents

Legacy motion and pose agents could still be enabled by request context and used
phrase/regular-expression parsing. They and their toggles were removed. Physical
requests now enter through model-authored Goals, Plans, and exact Capabilities.

### Memory meaning inferred from raw text

The compatibility MemoryAgent inferred stored meaning from raw text and keyword
rules. Memory updates now require a typed model-authored
`MemoryUpdateProposal`; the Host validates and applies that proposal without
reinterpreting the utterance.

### Capability-catalog semantic boosts

Catalog retrieval contained phrase-specific action scoring and forward-motion
special cases. Those boosts were removed. Retrieval may narrow candidates with
generic lexical evidence, while the model remains the final semantic authority.

### Weather-specific Host routing

Goal Interpretation contained weather-specific route repair and the legacy
ToolAgent inspected intent substrings and bypassed the common local-tool boundary.
Weather selection now requires exact model-authored
`capability:chromie.weather.lookup` identity, and the compatibility path crosses
`LocalToolExecutor`. Provider geocoding adaptation remains inside the Weather
Capability adapter.

### Host-authored truth and fallback speech

The interaction coordinator and several compatibility paths generated semantic
correction or route-specific wording in Host code. SpeakerAgent, MemoryAgent,
and ConversationAgent also contained fixed route acknowledgements, clarification
questions, pending-task interpretations, and emotional replies. These paths now
preserve validated model-authored speech, emit no invented wording, or use one
language-matched non-semantic operational failure when the model is unavailable.
User-facing ontology templates, default clarification text, weather-specific
fast-speech instructions, and default deep-thinking sentences were removed.
Normal wording belongs to Response Composer or another declared model speech
boundary.

### Conversation phrase classification

Conversation state inferred follow-up and new-topic semantics from phrase lists.
Those classifiers and environment overrides were removed. Explicit reset and
hard-idle expiry remain deterministic lifecycle controls; Goal Association owns
references and task continuity.

### Cognitive exception semantic classification

The Host inspected physical terms to choose an embodied-request fallback. Core
exceptions now return one language-matched non-semantic operational failure and
never infer the request class or authorize work.

### Duplicate execution boundary

The legacy ToolAgent called the weather Provider directly. It now crosses the
same `LocalToolExecutor` validation, timeout, identity, and evidence boundary as
`POST /tools/execute`.

### Canonical Capability terminology drift

Several active prompts, route DTOs, task proposals, traces, scenarios, and
qualification outputs still wrote executable `skill_id` or `skill_ids`. Current
outputs now use `capability_id` or `capability_ids`. Bounded readers still accept
retained historical artifacts, and conflicting dual identity fails closed.

### Static ontology as wording or execution authority

The high-level ability ontology still carried fixed bilingual speech templates,
Provider identifiers, default arguments, and timeout hints. It now records only
responsibility ownership and availability state. It neither speaks nor executes.

### Stale architecture and contract residue (follow-up 2026-08-03)

Five indexed staged-design or pre-Core planning documents still described
Router-proposed operations, Goal-Interpreter-selected task plans, Orchestrator
semantic consolidation, and migration-era proposal authority as if they were
current. They were removed and their index/Roadmap references now point
to the Goal-driven architecture and Cognitive Turn Loop. Current documentation
and scenario metadata were also aligned with
`fast_goal_interpreter_review_request`,
`goal_interpretation_action_confidence`, `interpretation_mode`, Cognitive
Gateway, and Agent-owned Cognitive Core terminology. The architecture constitution, Human-Like Interaction Contract, contributor
guide, Roadmap, and summaries now describe the implemented Gateway/Core split;
none claims that `/route`, a Goal Interpreter service, or pre-Goal task proposals
are current semantic or execution authorities.
The Router-removal guard now rejects these retired contract names and obsolete
documents across maintained docs and scenarios.

### Canonical runtime terminology and compatibility state

Current architecture, operations, contributor, scenario, and evidence text still
used **Skill Runtime** as though it were the canonical component and described
the rename as an unfinished migration. Current-facing text now uses **Trusted
Capability Runtime**. Legacy `SkillRuntime`, `SkillRequest`, `SkillResult`,
`skill_id`, and retained historical labels remain only at explicit compatibility
boundaries; no current document treats migration as open architecture work.

### Pre-Goal speech and evidence-summary contract drift

One maintained scenario still required the retired physical
`safety_prelude`/`needs_confirmation` fast-speech pair. The current contract
allows silence before authoritative Goals and Plans exist and accepts only the
route-valid, claim-free fast-speech schema. The scenario was renamed and turned
into a rejection regression for the stale pair.

A Cognitive Turn Loop fixture also expected deterministic speech from a generic
provider `summary`. The trusted fallback intentionally exposes only an explicit,
schema-committed `user_summary`; the fixture now matches that safety boundary
while the changed-schema tests continue proving that undeclared Provider output
cannot cross into speech.

### Test isolation and ownership drift

The complete suite exposed two stale test contracts. Automatic profile tests
inherited `CHROMIE_OPERATOR_MODE` from unrelated process state, making their
default-mode assertions order-dependent. Their subprocess environments now
clear inherited operator mode unless the test explicitly selects one. The
Python-source-reader ownership test duplicated an obsolete one-file allowlist
even though the authoritative registry already contained three reviewed tests;
it now compares discovery directly with that registry.

## Areas audited with no remaining violation found

### Benchmark purity

No maintained Benchmark runner or dataset was found selecting Agent Skills,
authoring runtime Plans, resolving discourse, injecting provider arguments, or
changing production Prompts/policy. Benchmarks remain evaluators of acceptable
behavior and evidence quality.

### Brain-body boundary

No current model-facing semantic branch selects behavior from simulator versus
physical backend identity. Chromie uses stable Capability contracts; Soridormi
owns backend choice, calibrated control, physical feasibility, stop, recovery,
and final physical refusal.

### Agent Skill authority

Repository Agent Skills remain read-only, digest-bound, owner-approved content.
They cannot import code, register Providers, grant permissions, authorize
Capabilities, bypass confirmation, or execute effects.

### Safety and operational controls

Deterministic stop/cancel, schema validation, authorization, confirmation,
resource conflict checks, evidence validation, timeout, and lifecycle controls
remain Host responsibilities. Phrase checks that only reject untrusted completion
claims or recognize explicit emergency/reset controls remain validation or
protective controls; they do not choose ordinary Goals or Capabilities.

## Mechanical protections added or strengthened

The repository policy gate now protects the corrected boundaries, including:

- removed Host deep-thinking delegation and phrase agents;
- no Host keyword Agent Skill selection;
- no catalog phrase-action boosts;
- no weather-specific Host route repair;
- no conversation follow-up/new-topic phrase classifiers;
- no raw-text memory inference;
- no static ability, SpeakerAgent, or MemoryAgent route-specific speech templates;
- no semantic ConversationAgent unavailable-model fallback;
- no direct ToolAgent weather-provider bypass;
- canonical current Capability identity in prompts, DTOs, task proposals, and
  evidence outputs.

## Automated evidence

Run:

```bash
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
python scripts/run_ruff.py
python scripts/run_mypy.py
python scripts/check_docs.py
./scripts/run_tests.sh
```

Automated checks establish implementation consistency only. The audited tree
passed 1,880 primary tests in 42.623 seconds, 20 legacy Agent tests, the Router
removal guard, repository policy checks, test-ownership checks, documentation
checks, runtime configuration/ownership/structure ratchets, JSON parsing, and
Python compilation. The pinned Ruff and Mypy executables were unavailable from
the restricted validation package mirror, so this audit does not claim a real
Ruff or Mypy run; their wrappers remain fail-closed and must run in the normal
developer environment with `requirements-test.txt` installed.

These checks do not replace clean source-bound live-text, positive Agent Skill
selection, provider-backed weather, MuJoCo, physical audio, or supervised
physical-robot evidence.

## Closure statement

All named implementation Issues from the handoff are complete, and the concrete
principle violations found by the original and 2026-08-03 follow-up audits are
corrected in the audited tree.
Remaining work is target-evidence collection under the existing authoritative
qualification documents, not another semantic architecture implementation
backlog.
