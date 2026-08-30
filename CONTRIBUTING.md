# Contributing to Chromie

Chromie combines realtime audio, local models, capability contracts, and
robot-safety boundaries. Small, well-evidenced changes are preferred over broad
refactors.

## Before editing

Read:

1. `docs/PROJECT_CHARTER.md`
2. `docs/STATUS.md`
3. `ROADMAP.md`
4. `DEVELOPMENT_CHECKPOINT.md`
5. the relevant component README
6. `docs/ACCEPTANCE.md` for the evidence level affected by the change

For commit, push, publication, or project handoff work, also follow the
[Chromie delivery-handoff skill](.agents/skills/chromie-delivery-handoff/SKILL.md).

## Development setup

For GPU-free control-plane work:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt
./scripts/run_tests.sh
```

Component-specific runtime dependencies are listed in each component’s
`requirements.txt`. The full voice stack additionally requires Docker, NVIDIA
Container Toolkit, Conda or an equivalent host environment, and audio devices.

## Change rules

- Follow the active Issue in `DEVELOPMENT_CHECKPOINT.md`. Until the canonical
  local gate is reproducible and the current-revision live voice loop is
  retained and the default target-evidence profile closes, feature,
  architecture, flag, and terminology growth is frozen except for work that
  closes those prerequisites or a demonstrated safety/provenance blocker.
- Keep microphone, playback, VAD, interruption, and Trusted Capability Runtime
  coordination in the host Orchestrator.
- Keep robot-body execution and physical safety in Soridormi.
- Do not expose raw motors, joints, torques, or actuator arrays to the LLM.
- Keep stop, cancel, emergency, silence, and unusable-audio decisions
  deterministic.
- Treat each semantic authority's primary LLM result as its sole writable
  semantic decision. Do not add reviewer, critic, coverage, rescoring,
  resegmentation, or semantic-repair calls at the same authority. Required
  grounding evidence belongs in the primary result; only one mechanically
  malformed DTO regeneration or one explicitly designated deeper-cognition
  delegation for genuine unresolved meaning is allowed under Project Charter
  principles 30–31. Before adding any model invocation, name its distinct owner
  and decision contract and show that it does not reinterpret upstream meaning.
- Add new side effects behind explicit policy, confirmation, monitoring, and
  default-off rollout gates.
- Preserve compatibility adapters until a documented migration and rollback
  path exists.
- Treat `agent-skills/` as passive reviewed prompt content: never add an
  executable entrypoint, provider registration, permission, confirmation
  exemption, phrase selector, or hidden mutable state. Regenerate and review the
  package digest after any content change.
- Do not use production `assert` statements for runtime, state, execution, or
  evidence invariants. Classify failure handling according to
  `docs/RUNTIME_FAILURE_PATHS.md`; expected cleanup may be debug-visible, while
  operational and evidence failures must fail closed or remain observable.
- Run `scripts/check_repository_policies.py` for stable architecture and
  deployment boundaries. Policy exceptions must be exact, reviewed, and recorded
  only in `config/repository_policy_exceptions.json`; stale exceptions fail.
- Prefer an existing owner over a new document, environment variable,
  compatibility path, or architectural term. Any necessary addition must name
  its owner, supported lifetime, validation, and the overlapping surface it
  replaces or why none can be removed. Report before/after counts when one of
  these repository surfaces grows.
- Treat defect analysis, implementation, explanation, and verification as one
  deliverable. A patch without a causal explanation is incomplete, even when
  the code is correct.
- Before a delivery commit is created or pushed, update
  `DEVELOPMENT_CHECKPOINT.md` and `HANDOFF.md` in the same commit. Record the exact
  scope, observed validation state, blockers, retained evidence, revision/profile
  identity, and next commands; do not leave the next session dependent on private
  chat history or stale passing claims.

## Required defect-fix report

Every user-reported or internally discovered defect fix must include a concise,
evidence-grounded report with all of the following:

1. **Observed failure and impact.** State what happened, what should have
   happened, and which user or system outcome was affected.
2. **Reproduction and evidence.** Identify the retained scenario, trace, log,
   failing test, or deterministic code path that demonstrates the defect.
3. **Expected contract and owner.** Name the contract that was violated and the
   component responsible for enforcing it.
4. **Actual workflow and module I/O.** Reconstruct the case from admitted input
   to the observed user-visible or system output. Include the actual synchronous,
   concurrent, and asynchronous branches rather than presenting a false linear
   pipeline. For every participating module through the first wrong boundary and
   the downstream containment or symptom, record its authority/role, authoritative
   input DTO or contract and material values/evidence, actual output DTO or effect,
   expected output, correlation/handoff, and a `correct`, `incorrect`, or `unproven`
   verdict. A compact report table should normally use this shape:

   | Order/branch | Module and owner | Authoritative input | Actual output | Expected contract/output | Verdict and evidence |
   |---|---|---|---|---|---|

   Add a flow or sequence diagram when fan-out, concurrency, delayed results, or
   Evidence re-entry matters. This must describe the reproduced episode, not just
   paste the generic architecture. Mark unavailable artifacts or values as unknown
   rather than inferring them; identify a materially absent/not-invoked stage; and
   redact private prompt, memory, credential, and personal data. After the change,
   state exactly which module input, output, validation, or handoff changed and why
   the other ownership boundaries remain unchanged.
5. **Root cause at the earliest responsible boundary.** Explain the causal chain
   from the initiating trigger to the first incorrect decision or state
   transition. Distinguish the root cause from downstream symptoms, unrelated
   failures, and contributing conditions. Use the benchmark attribution
   categories `scenario_or_oracle`, `prompt_or_profile`, `context_or_harness`,
   `contract_or_schema`, `runtime_or_provider`, `model_inference`, `mixed`, or
   `unresolved`, and cite the evidence that rules the other categories in or
   out. Separately record whether model-inference fault is `supported`,
   `not_supported`, or `unresolved`. A wrong model response is an initiating or
   contributing failure, not sufficient proof of an LLM root cause, when an
   owned validation, fallback, or workflow boundary was required to contain it.
6. **Fix mechanism.** Explain why the chosen change restores the violated
   contract, why it belongs at that boundary, and which behavior intentionally
   remains unchanged. Listing changed files or describing the diff is not a
   substitute for this explanation.
7. **Regression and evidence.** Show the pre-fix failure where practical, the
   focused post-fix regression, the broader gates run, and the highest evidence
   level actually reached. State any simulator, service, audio, or physical
   evidence still missing.
8. **Operational impact.** Report safety, compatibility, rollout, rollback,
   configuration, and documentation consequences when applicable.

A plausible story is not a root-cause finding. Each material claim must be tied
to retained evidence or clearly marked as an inference that still needs proof.
The final delivery may include a patch, commit, or pull request, but none of
those artifacts replaces the required explanation.

## Aggregate-first live iteration

When the current revision contains behavior changes that have not yet been
qualified, or when multiple live cases are due, the first live reproduction is
the complete directory-discovered cohort, not a sequence of case/edit/case loops.
Capture one clean source and deployed runtime identity, start the cohort once,
and keep that revision and runtime immutable until the runner finishes. Do not
change source, prompts, profiles, services, or scenario selection between cases.

After all selected cases finish, collect one post-cohort bundle:

```bash
./scripts/collect_debug_bundle.sh
```

Review the aggregate summary, every deterministic and semantic case (including
mechanical passes), and the single correlated bundle together. Group failures
by earliest responsible boundary before choosing a source change; do not treat
every utterance as an independent bug. A hard safety, provenance,
service-integrity, or safe-idle failure may terminate the run, but the retained
result is then an incomplete cohort, not a passing subset.

After aggregate diagnosis, a focused case is appropriate for validating one
proposed fix. Then run its ability class and the complete cohort again on the
changed revision before making another broad change or claiming the revision is
qualified. Focused runs accelerate a known iteration; they do not replace the
aggregate baseline or the post-change aggregate result.

## LLM-versus-workflow root-cause method

Any coding agent investigating Chromie, including an interactive Codex or
Claude Code session, must use the following method before changing a prompt,
model assignment, DTO, or workflow in response to model-driven behavior. The
goal is to locate the first incorrect boundary, not to infer causality from the
last spoken sentence.

1. Retain the original single- or multi-turn scenario, the expected contract,
   the observed user-visible result, the current Git revision, and the runtime
   profile. Do not simplify the utterance into an easier phrase before the
   failing run has been preserved.
2. Reproduce through the highest safe applicable profile. For an isolated
   retained defect, immediately collect the bounded runtime evidence so later
   calls do not push the failure outside the retained log window. For an
   aggregate iteration, do not collect or edit between cases; collect exactly
   once after the cohort finishes as required above:

   ```bash
   ./scripts/collect_debug_bundle.sh
   ```

3. Reconstruct the actual turn from the workflow artifacts: admitted input and
   Gateway decision; Goal Interpretation; the same-result Fast-Planner first
   Communicative Activity and concurrent Goal Association/remaining Fast planning;
   optional Deep planning when actually invoked; deterministic Goal binding;
   Trusted Capability Runtime and provider work; Host-bound Evidence re-entry into
   Fast Planner; and delivered speech or effect. Include optional Agent Skill and
   Social Attention branches only when present or materially absent. Record every
   participating module's authoritative input, actual output, expected output,
   correlation/handoff, and evidence verdict using the report table above. Show
   fan-out and asynchronous re-entry explicitly rather than forcing them into a
   chronological pipeline. Join records by `session_id`, `turn_id`, `trace_id`, and
   `call_id`; do not attach an unrelated startup warm-up or adjacent turn merely
   because it uses the same model, and do not invent a deprecated or skipped stage.
4. For every model call up to the first bad result, inspect the corresponding
   `llm_calls.jsonl` record and answer all of these questions:

   - Was the intended role sent to the intended model with the expected options,
     context budget, response schema, and prompt revision?
   - Did the exact prompt contain the necessary authoritative facts, current
     Goal and conversation state, capability evidence, and an internally
     consistent instruction? Check for missing, stale, duplicated, conflicting,
     or truncated material.
   - Did the raw model output preserve that meaning and satisfy the requested
     contract?
   - Did parsing, normalization, repair, validation, state application, or a
     later module change, drop, accept, or amplify the raw output?
   - If the model was wrong, was an owned deterministic or semantic validation
     boundary required to reject or contain that error?

5. Mark the earliest divergence with one primary category:

   | Category | Evidence required |
   |---|---|
   | `scenario_or_oracle` | The expected result conflicts with project authority, assumes unavailable state or capability, or overconstrains valid semantic variation. |
   | `prompt_or_profile` | Required guidance is missing, contradictory, wrongly projected, or truncated; the raw output is compatible with the defective prompt it received. |
   | `context_or_harness` | The prompt template is sound, but the run supplied stale, incomplete, cross-turn, fabricated, or incorrectly normalized state. |
   | `contract_or_schema` | The DTO/schema cannot express the valid result, admits a forbidden result, or repair/normalization changes otherwise valid model meaning. |
   | `runtime_or_provider` | The code calls the wrong model/endpoint, applies wrong options, times out or truncates, mismatches a response to a call, skips a required stage, or the provider fails. |
   | `model_inference` | The exact request is complete and internally consistent, the correct context/schema/provider path is proven, and the raw model output still violates a clear instruction or semantic contract. |
   | `mixed` | Two or more independently evidenced causes are necessary to explain the outcome; identify the initiating fault and the failed containment boundary separately. |
   | `unresolved` | Required prompt, raw output, correlation, state, or provider evidence is missing or ambiguous. Do not guess. |

6. Verify the classification against downstream behavior. A correct raw output
   that becomes wrong after parsing or state application is not a model fault. A
   wrong raw output caused by missing prompt facts is not isolated model fault.
   A wrong raw output plus a validator that was contractually required to catch
   it may be `mixed` even though the model initiated the failure. Another model
   passing the scenario is useful comparative evidence, but it does not prove
   the first model caused the original failure.
7. Retain the diagnosis with the scenario result. At minimum record the first
   wrong component, call/model/role/stage identifiers, the relevant prompt and
   raw-output evidence references, transformations or repairs, downstream
   containment, primary category, model-inference state, confidence, and
   remaining evidence gaps. Keep initiating trigger, root cause, downstream
   symptoms, and contributing conditions distinct.

The exact prompt and raw output can include private family conversation and
memory. Inspect them locally and cite bounded evidence references in reports;
never publish `llm_calls.jsonl` or an unredacted debug bundle without review and
sanitization. The benchmark-specific semantic verdict and attribution contract
is defined in [Chromie Benchmark Suite](docs/CHROMIE_BENCHMARK_SUITE.md#10-authoring-and-review-policy).

## Tests

Run the full dependency-light suite:

```bash
python scripts/check_repository_policies.py
./scripts/run_tests.sh
```

Add focused tests for contract, policy, cancellation, fallback, and concurrency
changes. GPU, audio, simulator, or hardware changes also require the relevant
higher-level evidence from `docs/ACCEPTANCE.md`.

## Documentation

Update documentation in the same change when behavior, defaults, interfaces,
status, or support scope changes. Run:

```bash
python scripts/check_docs.py
```

Use the four-axis vocabulary from `docs/STATUS.md`: implemented, automatically
verified, target validated, and release ready.

## Pull requests

A useful pull request description includes:

- the observed failure, violated contract, and ownership boundary;
- the actual workflow and per-module authoritative input/output up to the first
  wrong boundary and its downstream symptom or containment;
- the evidence-backed root cause at the earliest responsible boundary;
- the fix mechanism and why it restores the contract;
- safety impact;
- feature-gate/default changes;
- tests and target evidence;
- documentation updated;
- rollback behavior.

Never include execution tokens, private model credentials, device serials, or
unredacted acceptance logs.

## Static analysis

Run the pinned incremental static-analysis gates through `./scripts/run_tests.sh`. The reviewed scope, rules, and ratchet policy are documented in [Static Analysis Ratchets](docs/STATIC_ANALYSIS.md). Do not add blanket ignores or remove checked paths to make a gate pass.

## Test ownership

Behavior belongs in executable assertions, forbidden architecture in the repository policy checker, and literal source checks only in reviewed generated-artifact contracts. See [Test Ownership](docs/TEST_OWNERSHIP.md) and run `python scripts/check_test_ownership.py`.
