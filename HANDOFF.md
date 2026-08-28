# Chromie Latest Handoff

Audience: a coding agent or operator resuming the current semantic-authority closure.
Owner: project owner. Replace this snapshot when `DEVELOPMENT_CHECKPOINT.md` advances.
Authority: operational snapshot only; source, tests, retained evidence, and the
checkpoint remain authoritative.

## Repository state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Branch at start: `main`
- Starting commit: `7b4a25d8c8343b7f67509d3916e32272d6afc86f`
- Starting subject: `Add external architecture audit`
- Scope: close GI/GA/Planner same-authority review chains, remove the premature DBOS
  experiment, migrate general-ability acceptance to one scenario per file, and retain
  one post-change must-pass cohort
- Expected resume revision: the latest commit containing this handoff

Bootstrap on another machine:

```bash
git clone https://github.com/TimeTreker/chromie.git
cd chromie
git switch main
git pull --ff-only origin main
git status --short --branch
```

## What changed

GI no longer calls a second coverage model or performs certificate-driven source
resegmentation. The primary result now carries each Responsibility's inclusive source
token span together with its mode, bindings, Goal relationship, and sibling relations.
Trusted code checks only closed mechanics and provenance.

Logical call budgets are:

- resolved valid primary meaning: one `goal_interpretation` call;
- mechanically malformed primary DTO: one optional
  `goal_interpretation_contract_repair` call;
- genuinely unresolved meaning: one optional `goal_interpretation_deep` call;
- semantic or authority contradiction: fail closed without a reviewer;
- one mechanically malformed Deep location citation may use the one constrained
  `goal_interpretation_deep_contract_repair` allowed at that stage.

Repository policy now rejects the retired GI coverage stage/certificate/payload and
acceptance-wrapper names. Scenario fixtures contain explicit primary source evidence
and no longer expect semantic repair of noncanonical pace bindings.

GA now uses one `goal_association.primary` call for a valid result. Only a
Pydantic-invalid primary DTO may receive one `goal_association.contract_repair`; that
prompt receives the malformed object and exact validation errors, but no user turn,
candidate Goal projection, or identity context, and may not change semantics. The old
responsibility-coverage certificate, fresh interpretation, and final-audit model calls
and their DTO/schema/prompt/validation surfaces are removed. Grounding, Responsibility
conservation, binding, and continuity validation run deterministically after parsing and
fail closed without another model call.

Fast first response, Fast Advance, canonical Fast Plan, and Deep Plan now each require
their complete Goal/Evidence truth, exact wording, provenance, step ownership, and
satisfaction decision in the primary result. The separate truth qualifier, retained
response review, and coordinated Goal-coverage review calls are removed together with
their DTO/schema/prompt surfaces, `planner_audit.py`, dedicated truth-model client,
runtime health field, environment key, and warm-model role. Trusted validation remains
mechanical; one existing semantics-preserving DTO repair or a distinct Fast-to-Deep
escalation is not a second same-owner semantic review.

The DBOS misunderstanding is removed rather than preserved as a dormant compatibility
path. `CapabilityRuntime` directly tracks in-process `asyncio.Task` submissions; the
optional DBOS dependency, runtime-backend interface, DBOS adapter, model-facing
durability flag, and their tests are deleted. A future inter-process event transport
must start from a proven domain message contract instead of reviving this speculative
backend surface.

General-ability live acceptance no longer uses a central index. The former
`scenarios/general_ability_acceptance.json` is deleted and every scenario now owns its
metadata in one file beneath `scenarios/general_ability/`. Directory discovery currently
finds 50 must-pass, 15 core, and 8 challenge cases. The runner completes every selected
must-pass case and reports all failures before the stage gate can block core/challenge.
This layout is directly shardable and can later be imported into a database without
changing scenario identity or maintaining a second registry.

## Evidence ledger

Current automated evidence:

```text
python scripts/test_matrix.py goal-interpretation
Ran 38 tests ... OK

python scripts/scenario_runner.py \
  --suite goal_interpretation --suite cognitive_core_dialogue
Behavior scenarios: 31/31 passed

python scripts/check_repository_policies.py
Repository engineering policies passed (15 rule families, 0 reviewed exceptions)

./scripts/run_tests.sh
Ran 2023 tests ... OK
20 legacy Agent tests passed

python scripts/general_ability_acceptance.py --mode level-a \
  --ability-class robust_intent_understanding \
  --ability-class planner_goal_semantic_quality --no-write
General ability acceptance: 12/12 passed mode=level-a evidence=A

python scripts/check_docs.py
Documentation checks passed: 96 Markdown files
```

Pre-fix live iteration 50 on RTX 4090/Qwen3 4B remains diagnostic evidence only:
32/36 cases were contract-valid, four legacy coverage-stage calls returned HTTP 503,
and approximately 25/36 passed strict semantic judgment. It does not exercise or
qualify the new source.

The post-Planner-change 50-case must-pass aggregate is retained at
`.chromie/acceptance/general-ability/20260828T101824Z-live-text`: 8/50 machine passes,
42 hard failures, and no core/challenge start. Runtime identity SHA-256 is
`c8b3fc0991b72d38dade6c7b38020353199c04cc3126eaae735bd42c5e53c9cc`; the source tree
was dirty, so this is diagnostic C-preview evidence only. The valid post-cohort debug
bundle is `/home/chromie/Downloads/chromie_debug_bundle_20260828_183021.tar.gz`.
The retired Planner review families were absent; GA primary acceptance improved from
18/45 to 43/44 relative to the immediately preceding aggregate. Remaining clusters are
16 foreground-deadline failures, seven Runtime timeouts, four GA-stage failures, four
GI transport timeouts, and 26 fail-soft Social Attention timeouts. All 42 hard failures
were judged failed; manual semantic inspection of the eight mechanical passes also
rejects `capability_inventory_truthful` because it does not actually list a capability.
Independent multi-model semantic review, physical microphone/speaker evidence,
simulator execution, and physical robot evidence remain absent.

## Resume commands

Run local closure first:

```bash
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

Do not rerun isolated live cases before aggregate diagnosis. First close the reproduced
priority/resource-admission boundary inside existing owners: optional Social Attention
and TTS preparation must not compete ahead of GA/Fast/Deep critical-path work on the
single-parallel Ollama/GPU profile. Preserve GA and Fast Advance concurrency and avoid a
new merge barrier or semantic manager. After the focused source fix and local gates,
deploy one unchanged identity and rerun the complete 50-case must-pass stage once; do
not start core/challenges after a hard must-pass failure.

Typical deployment inspection commands remain:

```bash
docker compose build chromie-agent
docker compose up -d --no-deps chromie-agent
docker compose ps chromie-agent
ss -ltn '( sport = :8000 or sport = :5555 )'
```

The exact live profile/manifest commands are owned by `docs/ACCEPTANCE.md` and
`config/evidence_profiles.json`; do not copy a historical command if those authorities
have changed.

## Next evidence boundary

GI, GA, and Planner single-authority source closure is implemented. The aggregate now
identifies the next shared boundary as critical-path resource admission and foreground
latency, not another semantic reviewer and not yet model selection. Do not restore or
extend the removed GI, GA, or Planner same-authority review chains.

## Claim boundary

This is development-only. Automated tests prove the local contract, not current-model
semantic quality or live robot behavior. Historical live evidence may diagnose the old
chain but cannot qualify the new one.
