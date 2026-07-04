# Experience-To-Ability Learning

## Status

Design staged for future implementation. This document captures the decision
that reviewed daily experience should improve Chromie's ability usage,
planning, training data, scenario coverage, and ability roadmap. It is not
implemented as a realtime behavior path yet.

The current implemented foundation is:

- episode evidence recording;
- offline episode evaluation;
- good/bad/needs-review offline review records;
- scenario candidate mining;
- owner-review-only update proposals.

Those pieces are documented in
[Experience Evaluation and Scenario Mining](EXPERIENCE_EVALUATION_AND_SCENARIO_MINING.md).

## Core Decision

Experience retrieval alone is not the goal.

A small RAG-like layer that retrieves three similar cases and pastes them into
the prompt can help avoid repeated mistakes, but by itself it does not give
Chromie much new ability. The deeper goal is an experience-to-ability loop:

```text
daily interaction
  -> episode evidence
  -> offline review
  -> good/bad/needs-review case
  -> scenario/eval/training/missing-ability artifacts
  -> model, prompt, catalog, or skill improvement
  -> validation in scenarios and simulation
  -> deployment only when evidence improves
```

Experience should improve how Chromie understands, selects, plans, and requests
abilities. It should not pretend that an unsupported physical ability already
exists.

## Ability Meanings

The word "ability" has two different meanings in this system.

| Kind | Example | What experience can do |
|---|---|---|
| Existing executable ability | `soridormi.blink_eyes` already exists | Learn when to select it, which arguments to use, and what not to say. |
| Missing desired ability | Users often ask to control a light, but no light skill exists | Propose a missing ability, scenario coverage, catalog requirement, and future implementation task. |

Experience can guide interpretation and propose new work. Runtime execution
still requires declared abilities, schema validation, confirmation gates,
Skill Runtime authorization, and Soridormi or tool-provider evidence.

## Products Of Experience

Reviewed daily experience should produce several different artifacts, not one
generic memory blob.

| Artifact | Purpose |
|---|---|
| Regression scenario | Deterministic test that prevents a known mistake from returning. |
| Positive scenario | Demonstrates a good behavior pattern that should stay stable. |
| SFT example | Input and correct structured output for Router or planner training. |
| Preference pair | Chosen correct behavior and rejected bad behavior for DPO/RLHF-style tuning. |
| Missing ability proposal | Evidence that users need a capability Chromie does not currently have. |
| Skill catalog improvement | Better descriptions, parameters, examples, or availability boundaries for an existing skill. |
| Simulation curriculum item | A high-level task that Soridormi can turn into simulator rollouts when the physical behavior exists. |
| Experience case card | A compact, reviewed behavioral precedent that may be retrieved into future prompts. |

The case card is useful, but it is only the short-term bridge. The main value is
turning reviewed experience into better models, better tests, better skill
contracts, and better robot capabilities.

## Experience Case Cards

If a retrieval layer is added, it should retrieve compact reviewed behavioral
precedents, not raw logs or raw scenario JSON.

Example:

```json
{
  "case_id": "exp_blink_not_roleplay",
  "status": "approved",
  "trigger": "User asks Chromie to blink her eyes.",
  "interpretation": "This is a physical robot skill request.",
  "preferred_behavior": "Emit soridormi.blink_eyes with count if specified.",
  "forbidden_behavior": "Do not say or roleplay that blinking happened without a blink skill.",
  "skills": ["soridormi.blink_eyes"],
  "source": "reviewed_scenario",
  "confidence": 0.95,
  "requires_owner_approval": true
}
```

Prompt-facing form:

```text
Relevant Reviewed Experience:
- Blink requests should map to soridormi.blink_eyes when the skill is available.
  Speech-only roleplay is wrong.
- A compound request such as walking while telling a joke should keep speech as
  a chromie.speak task alongside motion, not drop the speech task.
```

These notes are advisory. They do not authorize execution.

## Safety Boundaries

Experience may:

- help interpret user intent;
- suggest likely ability classes;
- improve skill selection examples;
- draft scenarios and training examples;
- propose new abilities when repeated requests reveal a capability gap;
- improve prompt, model, catalog, or simulator curricula after review.

Experience must not:

- authorize physical execution;
- bypass confirmation, preflight, policy, schema validation, or provider checks;
- turn raw logs into prompt payloads;
- auto-apply safety policy or core principle changes;
- claim a missing physical skill exists;
- overwrite operator-reviewed scenario truth.

## Future Implementation Plan

### Stage 1: Artifact Export

Extend the offline evaluator so reviewed cases can export structured artifacts:

- `experience_case_cards.jsonl`;
- `sft_examples.jsonl`;
- `preference_pairs.jsonl`;
- `missing_ability_proposals.jsonl`.

Missing-ability artifacts should be derived from shared task-proposal ledger
entries with `proposal_kind=ability`, `state=missing_ability`, and an
`ability_id`, not from raw transcript guesses.

Every generated artifact should carry source episode, evaluation, review, and
scenario IDs. Anything that affects runtime behavior remains owner-review-only.

### Stage 2: Reviewed Case Store

Create a small local reviewed-case store:

- only approved case cards are retrievable;
- cards store compact triggers and behavior guidance;
- raw episodes stay in the evidence journal;
- retrieval uses semantic similarity plus explicit tags such as `blink`,
  `compound_action`, `missing_skill`, `speech_truthfulness`, and `safety_hold`.

### Stage 3: Prompt Injection Experiment

Inject the top few approved case cards into Router and deepthinking prompts as
advisory experience context.

Acceptance rule: the retrieved cases must improve behavior scenarios without
increasing false positives, latency beyond budget, or unsafe authorization.

### Stage 4: Training Dataset Gate

Convert approved scenarios and reviewed cases into SFT and preference datasets.

The training gate should check:

- schema-valid target outputs;
- no raw motor, joint, torque, or low-level controller fields;
- no unapproved personal or private data;
- clear chosen/rejected distinction for preference pairs;
- scenario-run improvement before model promotion.

### Stage 5: Missing Ability Roadmap

Aggregate repeated missing-ability proposals into a capability roadmap:

- requested behavior;
- frequency and source cases;
- required provider or Soridormi support;
- safety and confirmation policy;
- simulation evidence needed before runtime support.

This turns "users keep asking for X" into a clear engineering backlog instead
of a hallucinated skill.

## Acceptance Criteria

The future implementation is useful only if it proves more than retrieval:

- approved reviewed cases can export case cards, SFT examples, preference
  pairs, and missing ability proposals;
- case retrieval improves scenario pass rate without granting execution
  authority;
- SFT/preference exports validate against Router or planner output contracts;
- missing ability proposals are visible to humans and never executed as skills;
- full Level A tests and behavior scenarios pass after any prompt or model
  change;
- simulator or target evidence is required before claiming a new physical
  ability.

## Non-Goals

- Do not build autonomous self-modification.
- Do not train low-level motion policies from language scenarios alone.
- Do not replace scenario tests with LLM judgment.
- Do not make experience memory a hidden rule table.
- Do not deploy new physical abilities without Soridormi evidence.
