# LLM Prompt Qualification and Optimization Method

Status: Required method for qualifying or optimizing a Chromie semantic-model role

Audience: project owners, coding agents, prompt reviewers, benchmark authors, and
operators qualifying Goal Interpretation, Goal Association, Fast/Deep Planner, or
another bounded LLM authority

Owner: Chromie prompt-qualification methodology. The component prompt, DTO, Schema,
Host validator, benchmark corpus, and acceptance documents remain authoritative for
their own facts.

This document is the reusable method distilled from the completed Goal
Interpretation (GI) and Goal Association (GA) prompt investigations. It exists as a
separate owner because no existing document owns the complete cross-component
sequence from authority audit through frozen-corpus inference, adjudication,
root-cause classification, minimal iteration, full rerun, and handoff. It does not
replace [Scenario-Driven Development](SCENARIO_DRIVEN_DEVELOPMENT.md), the
[Benchmark Suite](CHROMIE_BENCHMARK_SUITE.md), the
[LLM-versus-workflow root-cause method](../CONTRIBUTING.md#llm-versus-workflow-root-cause-method),
or [Acceptance and Evidence](ACCEPTANCE.md); it composes them into one prompt-specific
operating protocol.

Coding agents apply this method through the
[Chromie LLM Prompt Qualification Skill](../.agents/skills/optimize-chromie-llm-prompt/SKILL.md).
The Skill is an execution entrypoint; this document remains the binding method.

## 1. Objective

Prompt work is complete only when evidence shows that the exact model transaction
produces the role's intended semantic result through its real structured-output and
Host boundaries. The objective is not to make a sample answer look better. It is to
qualify a complete model-role transaction:

```text
authoritative input and bounded context
  -> global truth projection + role-local decision procedure
  -> exact dynamic response Schema
  -> one primary model result
  -> parsing and deterministic validation
  -> Host-owned state transition or fail-closed result
```

The unit under evaluation is therefore:

```text
model + global prompt projection + local prompt + context projection
+ DTO/Schema + decoder transport + deterministic Host boundary
```

A candidate model passing a simplified probe does not qualify the production prompt.
A mechanically valid JSON object does not qualify semantics. A good semantic answer
that the DTO cannot express does not prove the prompt is wrong. A downstream success
after semantic repair does not qualify the primary result.

## 2. Binding principles

1. **Declare one semantic authority.** State exactly what the role may decide and
   what belongs upstream, downstream, or to deterministic safety/runtime code.
2. **Evaluate the real transaction.** Use the exact production prompt projection,
   dynamic Schema, DTO, parser, and Host validator whenever the evidence claim names
   that transaction.
3. **Keep one primary semantic result.** Do not add a second LLM call to judge,
   complete, resegment, score, or repair the same role's decision. A mechanically
   malformed DTO may use only the narrowly permitted repair in project policy; it
   may not reinterpret meaning.
4. **Freeze before measuring.** Bind source revision, corpus tree, prompt and Schema
   digests, model identity, parameters, and inference protocol before a full batch.
   Do not edit between cases.
5. **Hide the answer from the candidate.** Reference outputs, rubrics, expected
   categories, and adjudication labels must not enter candidate inference packets.
6. **Separate hard facts from semantic judgment.** Schema, source conservation,
   IDs, capabilities, safety, evidence, and state transitions are deterministic.
   Meaning and naturalness use declared semantic dimensions.
7. **Fix the earliest responsible boundary.** A prompt edit is justified only for
   a prompt defect. Context, Schema, DTO, Host, provider, model, or oracle defects
   are fixed at their own owners.
8. **Optimize an ability class, not a phrase.** Scenarios are probes into general
   reasoning and continuity. Runtime phrase tables and scenario-ID branches are
   forbidden.
9. **Focused reruns diagnose; full reruns qualify.** Every changed candidate must
   return to the complete frozen cohort before a revision-level claim.
10. **State the evidence ceiling.** Offline Codex inference, deployed live text,
    simulator evidence, voice evidence, and physical-robot evidence are different
    claims.

## 3. Global truth and role-local prompt ownership

Chromie's identity, worldview, value boundaries, robotic embodiment truth, safety
principles, and stable Mind are global facts. They must remain independent of one
model role. A role prompt may receive a bounded projection of those facts, but it
must not redefine them locally.

Classify every proposed prompt change before editing:

| Change class | Owner and required action |
|---|---|
| Global identity, worldview, values, embodiment truth, or constitutional authority | Update the existing canonical Project Charter, interaction contract, or Mind-profile owner only with project-owner authorization; rerun every affected model role. |
| Role-local decision procedure, field meaning, examples, or ordering | Change the existing component prompt owner and qualify that role's complete frozen cohort. |
| Missing or stale runtime context | Fix the context projection/harness; do not paste fabricated state into the static prompt. |
| Valid meaning cannot be represented, or forbidden meaning is admitted | Fix the DTO/dynamic Schema/validator contract with explicit architecture authority; do not work around it with wording. |
| Transport, decoder, timeout, truncation, or wrong-model problem | Fix and qualify the provider/profile boundary. |
| Complete request, sound contract, wrong raw result | Retain as model-inference evidence; compare or change the model only under the model-qualification process. |

One role's cohort may expose a global defect, but it does not authorize silently
changing shared truth. Record the conflict in the active Issue, preserve the failing
case, and obtain owner authorization before crossing the global boundary.

## 4. Required artifacts

Every qualification must retain or identify:

- active Issue and working branch;
- pre-change revision and evaluated source state;
- semantic owner and exact authoritative input/output contract;
- production prompt source and all runtime prompt variants;
- dynamic response Schema and DTO/Host validation path;
- one authoritative scenario per file;
- aggregate manifest with counts, language/category/split coverage, provenance,
  training eligibility, and a deterministic scenario-tree digest;
- frozen candidate input packet for every case;
- exact model, role, reasoning/decoding settings, provider/transport, timeout, and
  retry/repair policy;
- raw output, parsed output, Schema verdict, Host verdict, semantic verdict, failure
  classification, and evidence references per case;
- aggregate summaries for baseline, focused reruns, and final full rerun;
- prompt and Schema hashes for every claimed iteration;
- exact validation commands and observed results;
- remaining blockers and claim boundary.

Scenario files are the reviewable source units. A generator, database, or combined
report may assist authoring or execution, but it must not become the only source of
scenario truth. Generated scenarios remain ineligible for training until independent
review explicitly changes their provenance.

## 5. The qualification and optimization loop

### Phase 0 — establish authority and permission

Before creating scenarios or changing text:

1. Read `AGENTS.md`, the Project Charter, Human-Like Interaction Contract, Status,
   Roadmap, checkpoint/handoff, this method, the component prompt/DTO/Schema/Host
   source, its tests, and relevant acceptance rules.
2. Write one sentence for what the role owns and one sentence for what it must not
   own.
3. List every actual model invocation in the transaction, including conditional
   deep cognition, streaming/re-entry modes, and permitted mechanical repair.
4. Identify any conflict with a Project Charter principle. Stop and request explicit
   authorization before violating or amending it.
5. Define the evidence claim and the maximum evidence level this run can support.

The output of Phase 0 is an authority map, not a proposed prompt rewrite.

### Phase 1 — reconstruct the real transaction

Trace one representative case from admitted input through the first state mutation.
For each boundary, record:

| Boundary | Required record |
|---|---|
| Upstream owner | Exact accepted DTO, material values, source/evidence refs, and correlation IDs |
| Prompt projection | Exact global, static, dynamic, contextual, and capability sections actually sent |
| Decoder | Exact Schema, allowed IDs/enums/constants, and output budget |
| Model call | Model/role/options, raw output, termination reason, latency, and call identity |
| Parser/normalizer | Parsed value and every deterministic transformation |
| Validator/Host | Accepted/rejected result, state transition, failure class, and containment |
| Downstream owner | Whether it was invoked and what authoritative result it actually received |

Do not infer the prompt from a template alone. Runtime projections, dynamic constants,
catalog compaction, previous-turn state, and response Schema are part of the request.
Do not infer model failure from the final spoken response alone.

### Phase 2 — design a frozen contrast corpus

Build the corpus from the role's real input surface, not generic chatbot questions.
Use contrast sets so one semantic seed changes one important condition at a time.
Useful axes include:

- English and Chinese;
- no prior state versus bounded existing state;
- single versus multiple independent outcomes;
- resolved versus genuinely unresolved information;
- continuation, correction, cancellation, confirmation, rejection, pause, resume,
  supersession, merge, split, and terminal reference;
- direct conversation, information acquisition, physical work, and mixed modes;
- available, unavailable, degraded, unsafe, or conflicting capabilities;
- fresh turn, multi-turn continuation, execution Evidence re-entry, and Situation
  revision;
- ordinary, boundary, adversarial, and retained historical-regression cases.

For every scenario:

1. Store the complete production-shaped input in its own file.
2. Declare deterministic invariants, semantic dimensions, acceptable variation,
   forbidden outcomes, and expected evidence.
3. Keep reference output separate from the candidate prompt.
4. Validate the reference through the exact current Schema and Host when it claims
   current-contract compatibility.
5. Mark a valid but unrepresentable case as a known contract gap. Never distort the
   reference into a representable but semantically wrong answer.
6. Keep whole contrast sets inside one split and bind the sorted tree to a digest.
7. Record author/reviewer provenance and `training_eligible=false` by default.

Reference outputs are candidate oracles, not automatic truth. Reviewers must be
allowed to find that a reference, rubric, or grader is wrong.

### Phase 3 — run one immutable baseline batch

Freeze the corpus and source before inference:

```text
one source state
  + one prompt/Schema identity per runtime variant
  + one declared model/role/protocol
  + target-blind candidate packets
  -> complete batch
```

Requirements:

- use the inference authority requested by the project owner; never silently
  substitute a smaller local model;
- execute one primary semantic invocation per scenario through the exact prompt and
  Schema envelope;
- retain all outputs, including malformed, rejected, timed-out, and seemingly
  correct results;
- do not change source, prompt, Schema, references, or adjudication during the batch;
- mark an interrupted batch incomplete rather than combining it with a later source
  state;
- record source stability and per-case attempt counts.

When Codex performs both inference and later review, keep those as separate phases
and exclude targets from inference, but label the result same-model and
non-independent. It is strong diagnostic evidence, not independent release closure.

### Phase 4 — adjudicate after the complete batch

Apply evidence in this order:

1. **Transport integrity:** correct call/model/role, complete response, no truncation,
   timeout, cross-call mismatch, or hidden retry.
2. **Dynamic Schema:** exact structured-output validity for that scenario.
3. **DTO and deterministic Host:** source/Responsibility/Goal conservation, allowed
   IDs, capability schemas, safety, confirmation, evidence, state transition, and
   fail-closed behavior.
4. **Semantic dimensions:** meaning, completeness, continuity, uncertainty,
   naturalness, and role-specific quality.
5. **Aggregate coverage:** category, language, split, runtime variant, repair count,
   hard-failure family, and latency distribution.

A deterministic hard failure cannot be averaged into a pass. A semantic reviewer may
explain a hard failure but cannot override it. Preserve per-case adjudication, not only
an aggregate percentage.

### Phase 5 — classify the earliest divergence

Use exactly one primary class unless independent evidence requires `mixed`:

| Classification | Typical evidence | Correct fix owner |
|---|---|---|
| `scenario_or_oracle` | Reference conflicts with canonical authority or overconstrains valid variation | Scenario/rubric/reference |
| `prompt_or_profile` | Required instruction is absent, contradictory, badly ordered, wrongly projected, or truncated | Existing prompt/profile owner |
| `context_or_harness` | Template is sound but supplied state is missing, stale, fabricated, or normalized incorrectly | Context projection/benchmark harness |
| `contract_or_schema` | Valid meaning is impossible to express, forbidden shape is admitted, or normalization changes meaning | DTO/Schema/validator, with architecture authorization |
| `runtime_or_provider` | Wrong endpoint/model/options, timeout, truncation, call mismatch, skipped stage, provider failure | Runtime/provider/profile |
| `model_inference` | Exact request is complete and consistent, but raw output violates it | Model qualification/selection |
| `mixed` | More than one independently proven cause is necessary | Fix the initiating boundary and failed containment separately |
| `unresolved` | Required prompt, raw output, correlation, or downstream evidence is unavailable | Retain gap; gather evidence before editing |

Also distinguish:

- initiating trigger;
- root cause;
- downstream symptom;
- failed or successful containment;
- contributing conditions;
- remaining evidence gaps.

The last visible failure is often not the root cause.

### Phase 6 — select one minimal general fix

Cluster failures by their earliest shared boundary. Select one cluster and one
testable hypothesis.

For a local prompt defect:

- move the relevant rule close to the decision it constrains;
- make field ownership and forbidden substitutions explicit;
- remove contradictory or redundant wording before adding more text;
- prefer a decision procedure and result conditions over lists of example phrases;
- preserve global identity/value truth and downstream authority;
- keep the prompt within the actual context budget.

For a Schema/contract defect:

- make the earliest decoder boundary express the already authoritative invariant;
- reject missing semantic material before Host state mutation;
- do not ask a later model or Host normalizer to invent the missing meaning;
- if the current DTO cannot express a valid complete result, record a global blocker
  and obtain owner authorization before redesign.

Do not change the prompt merely because a case failed. Do not change multiple prompt
layers, the model, the Schema, and the oracle in one iteration unless evidence proves
they are one inseparable root cause.

### Phase 7 — focused proof, then full qualification

After the minimal change:

1. Run contract/unit tests for the repaired earliest boundary.
2. Rerun the exact baseline failures or one representative cluster.
3. Confirm that the failure changes for the predicted reason.
4. Rerun the entire frozen cohort with no source edits between cases.
5. Re-adjudicate every case, including mechanical passes.
6. Compare baseline and candidate by category, language, hard failures, semantic
   dimensions, repair attempts, and latency.
7. Run the applicable general-ability class and canonical repository gates.

If the focused rerun passes but the full cohort regresses, reject or revise the
change. Do not declare the prompt qualified from the focused subset.

### Phase 8 — stop deliberately

Stop prompt iteration when all of these are true for the declared scope:

- all deterministic hard gates pass;
- the predeclared semantic threshold or per-case requirement is met;
- no category, language, runtime variant, or important ability regressed;
- no forbidden same-authority repair or hidden retry was introduced;
- remaining failures are classified with evidence and do not share an unresolved
  prompt boundary;
- prompt/schema hashes and the final source state are retained;
- the applicable focused tests and full gates pass;
- the evidence ceiling and open blockers are explicit.

Stop early when a new iteration only makes wording broader without repairing an
evidenced boundary, or when reviewer analysis recommends no prompt change and
remaining differences are oracle/model/contract issues. A maximum iteration budget
is a safety bound, not a target to consume.

## 6. Lessons retained from GI and GA

These results demonstrate the method; they are not permanent release thresholds.

| Investigation | What happened | Reusable lesson |
|---|---|---|
| GI daily-life cohort | 1,496 bilingual, production-shaped cases were kept as separate files and organized into contrast sets. Broad prompt experiments regressed decomposition/source semantics; the selected fifth iteration retained 1,496/1,496 Schema/Host passes and no further prompt-change recommendation. Some reference and reviewer judgments were themselves wrong. | More prompt text is not automatically better. Protect source truth, audit references and graders, compare whole contrast sets, and stop when remaining errors are not a shared prompt boundary. |
| GI genuine-unresolved subset | The 68 source-based Deep-GI cases were qualified separately from the resolved primary path. | Conditional deeper cognition needs its own input contract, corpus, and claim; do not average it into the common path. |
| GA baseline | The target-blind Codex batch passed the then-current dynamic Schema in 1,500/1,500 cases, but 36 `modify_active` results failed the real Host because the semantic change existed only in `reason_summary`. | Schema pass alone is insufficient. Always execute the downstream DTO/Host boundary and compare authoritative field ownership. |
| GA local fix | The existing semantic-update invariant was moved into dynamic Schema and next to relationship selection in the local prompt. The exact 36 failures passed, then the full supported cohort passed 1,400/1,400 with zero repair attempts. | Align prompt and decoder at the earliest boundary; prove the hypothesis on failures, then rerun the complete frozen cohort. |
| GA global contract fix | 100 cases required continuing one Goal and creating an independent Goal in one turn, but the exclusive `associate | create_goals` DTO could not express both. After explicit owner authorization, the redundant discriminant was removed; candidate-aware GA now writes both non-exclusive collections directly, and decoder/Host conservation requires each GI Responsibility exactly once across their union. All 1,500 corpus references then passed the exact Schema/DTO/Host path. This is mechanical offline contract evidence; target-blind model inference was not rerun by that result. | Never optimize wording around an impossible output contract. Preserve the scenario, escalate the global DTO decision, repair the earliest representational boundary, and keep source closure distinct from model qualification. |
| Same-model Codex review | Codex supplied strong offline inference and post-hoc judgment, but the reviewer was not independent and occasionally misread valid Schema fields. | Retain same-model judgment as diagnostic evidence and keep its errors visible; independent qualification remains a separate claim. |

The retained corpora are:

- [Goal Interpretation Daily-Life Dataset](../benchmarks/datasets/goal_interpretation_daily_life/README.md)
- [Goal Association Daily-Life Corpus](../benchmarks/datasets/goal_association_daily_life/README.md)

## 7. Applying the method to Fast and Deep Planner

Fast and Deep are cognition-depth passes of one Planner HOW authority, not two
independent planners and not mutual reviewers. Qualify them in order while preserving
one shared Planner contract:

```text
Fast primary/common path
  -> Fast streaming advance and bounded re-entry variants
  -> Deep complex/blocked/revision path
  -> combined Planner regression
```

### 7.1 Planner input surface

Planner scenarios must use production-shaped inputs containing, as applicable:

- accepted GI Responsibilities and source evidence;
- GA-committed canonical Goals and their lifecycle/open gaps;
- exact available Capability and Agent Skill projections;
- current Plan/Work state and Planner re-entry scope;
- trusted Evidence and Situation revisions;
- discourse referents, bounded Memory, interaction mode, and confirmation state;
- safety/resource/concurrency constraints;
- prior delivered or scheduled Communicative Activity when deduplication matters.

Do not give Planner a reference Plan, expected Capability, rubric label, or hidden
normalized argument in the inference packet.

### 7.2 Planner output dimensions

Use deterministic gates for:

- complete per-Goal coverage and exact Goal ownership;
- disposition, plan relation, Goal outcomes, satisfaction, and unresolved material;
- step IDs, Capability IDs, argument Schema, and source Goal IDs;
- parameter-resolution provenance and whether a blocking value is actually resolved;
- dependency, sequential/parallel timing, resource, confirmation, and safety contracts;
- truthful response text and Evidence scope;
- no premature completion speech;
- no duplicate Communicative Activity after early Fast presentation;
- revision/re-entry scope and no replay of closed siblings;
- no executable partial plan after a hard validation failure.

Use semantic review for:

- whether the Plan completely and naturally realizes the Goals;
- whether chosen Capabilities and arguments are appropriate alternatives;
- whether clarification, escalation, refusal, or unavailability is genuinely needed;
- whether response wording is concise, grounded, and consistent with the Plan;
- whether Deep reasoning improves a complex case without inventing work.

### 7.3 Suggested frozen contrast families

Fast Planner should cover at least:

- direct truthful conversation with no effect Work;
- one complete common Capability action;
- multiple compatible Goals;
- information acquisition followed by evidence-grounded response;
- explicit and defaulted parameter resolution;
- confirmation-held material alternatives;
- unavailable or invalid Capability;
- early Communicative Activity plus later GA binding;
- streaming advance and terminal Fast result;
- ordinary Evidence/Situation/time re-entry;
- Social Attention as optional subordinate activity;
- cancellation/supersession containment.

Deep Planner should cover at least:

- compound or constrained multi-Goal Work;
- Fast semantic escalation with no leaked executable partial result;
- blocked, degraded, failed, or unsafe Situation re-entry;
- plan revision after new Evidence or changed Goal truth;
- capability/resource/concurrency conflict and complete alternative;
- consequential ambiguity requiring genuine clarification;
- incomplete observation requiring acquisition Work;
- confirmation and cancellation across a revised Plan;
- complex Agent Skill composition;
- cases where no change or no safe Plan is the correct result.

Create one independently reviewable scenario file per case and keep Fast/Deep contrast
sets together across the same semantic seed. Qualify Fast first because it is the common
path and shares prompt/contract material with Deep. After Deep changes, rerun both Fast
and Deep cohorts.

### 7.4 Planner-specific failure traps

- A valid JSON Plan with missing Goal coverage is a hard contract failure.
- A correct Capability with guessed consequential arguments is not a semantic pass.
- Deep recovery does not erase a technical Fast failure.
- Fast/Deep may not judge or repair each other's meaning.
- A mechanical repair may fix structure only; it may not choose new Work.
- Host validation may reject or contain a Plan but may not substitute a Capability,
  fill semantic arguments, or rewrite Plan meaning.
- Exact plan equality is usually too narrow; use deterministic invariants plus an
  acceptable semantic region.
- Latency is compared only after semantic, safety, and evidence correctness.

## 8. New-session start protocol

A new coding session should read, in order:

1. `AGENTS.md`
2. `docs/PROJECT_CHARTER.md`
3. `docs/HUMAN_LIKE_INTERACTION_CONTRACT.md`
4. `docs/STATUS.md`
5. `ROADMAP.md`
6. `DEVELOPMENT_CHECKPOINT.md`
7. `HANDOFF.md`
8. this document
9. `docs/SCENARIO_DRIVEN_DEVELOPMENT.md`
10. `docs/CHROMIE_BENCHMARK_SUITE.md`
11. `docs/ACCEPTANCE.md`
12. the target component prompt, DTO, Schema, Host, and focused tests

The project owner can start a Planner-prompt session with:

```text
Follow docs/LLM_PROMPT_QUALIFICATION_METHOD.md as the binding method.
Optimize the Fast Planner prompt first, then Deep Planner, while preserving one
Planner HOW authority. Reconstruct the real production input/prompt/Schema/Host
transaction before editing. Create a frozen bilingual daily-life contrast corpus
with one scenario per file, keep targets out of inference packets, and use Codex
as the declared offline inference authority unless I explicitly approve another
model. Run one immutable full baseline, adjudicate every result, classify the
earliest wrong boundary, make one minimal general fix, rerun the exact failures,
then rerun the complete frozen cohort. Do not hide DTO/global contract gaps with
prompt wording, do not add a second semantic judge/repair call, and do not claim
deployed, voice, simulator, robot, or release evidence from offline inference.
Record prompt/Schema/model/source identities, tests, blockers, and the exact
evidence ceiling in the Issue and delivery handoff.
```

Before implementation, the new session must report:

- Planner authority and non-authority;
- exact Fast/Deep invocation variants;
- proposed corpus matrix and split policy;
- deterministic and semantic adjudication dimensions;
- expected evidence level;
- any global prompt/DTO/architecture question requiring owner authorization.

## 9. Definition of done

A prompt-optimization delivery is complete only when:

- the real model-role transaction and earliest boundaries are documented;
- the corpus is frozen, directory-discovered, digest-bound, and independently
  reviewable per file;
- candidate inference is target-blind and source-stable;
- every case has retained raw/parsed/Schema/Host/semantic evidence;
- failures are classified before editing;
- the fix is general and belongs to the evidenced owner;
- the exact failure cohort and complete frozen cohort were rerun;
- regressions, repair counts, and hard failures are explicit;
- focused tests, applicable ability tests, and canonical gates pass;
- global contract gaps and non-independent review remain visible;
- the Issue, checkpoint, and handoff allow another session to resume without chat
  history;
- the final claim names exactly what was and was not qualified.
