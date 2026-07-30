# Cognitive Gateway/Core Source-Bound Qualification

Status: maintained specialized target-evidence track; coordinated by [Target Evidence Closure](TARGET_EVIDENCE_CLOSURE.md).

This procedure validates the implemented interaction authority boundary against
running services and Soridormi/MuJoCo. It does not add cognition, infer expected
intent from user text, select a model, or grant release readiness.

## Qualification claim

A passing bundle may support this narrow claim:

> The evaluated Chromie revision admitted or suppressed each retained turn at the
> Cognitive Gateway before ordinary semantic interpretation, used the Goal-Driven
> Cognitive Core as the single semantic authority for admitted turns, preserved
> trusted tool evidence across a follow-up, cancelled an active Goal only after
> its Soridormi provider request had started, executed the retained compound body
> request through the evaluated Soridormi `sim` endpoint, and returned to an
> explicitly reported safe-idle state after both normal completion and cancellation.

A passing bundle is not evidence of physical-robot operation, microphone or
speaker quality, unattended autonomy, or release readiness.

## Evidence identity

Qualification starts from a clean committed Chromie checkout. The identity
capture binds:

- exact Chromie revision and clean-worktree state;
- generated runtime-profile digest and fingerprint;
- launcher-effective cognitive model topology;
- running Agent, LLM, ASR, and TTS container image IDs;
- the Agent container's effective runtime fingerprint and models;
- capability-manifest digests and paired Soridormi revision;
- Compose files and launcher runtime overrides.

The normal launcher may intentionally override profile-planned cognitive models,
for example when CosyVoice uses one resident `qwen3:4b` model. Qualification
compares the running Agent with that launcher-effective topology, not with the
unmodified hardware-profile plan.

Missing, dirty, stale, mismatched, or digest-invalid identity fails closed. An
identity generated with `--allow-dirty` or `--allow-missing-images` is diagnostic
only and cannot qualify this target-evidence track.

## Retained live-service text cases

The versioned manifest is
`benchmarks/manifests/cognitive_gateway_core_qualification_v1.json`. Its inputs
are sent unchanged to the maintained text entrypoint. Expectations are evaluated
only after the run.

The retained set covers:

- inactive ambient speech suppressed before Core entry;
- deterministic `Stop.` reflex dispatch without ordinary Core interpretation;
- a direct question admitted to the Core;
- Beijing weather lookup through the tool lane;
- an elliptical follow-up that reuses recent trusted tool evidence, targets the
  prior semantic Goal, and does not repeat the lookup.

No scenario ID, expected lane, expected skill, or expected answer is passed to
Chromie's cognitive models.

## Retained active-Goal cancellation case

The cancellation runner starts the manifest-owned walking request through the
authoritative Gateway/Core and trusted Skill Runtime path. It waits on a bounded
read-only Skill Runtime observation until `soridormi.walk_velocity` has actually
entered its Provider, then sends the exact manifest-owned `Stop.` turn through
the normal Gateway. Qualification requires:

- a non-empty semantic Goal binding on the started request;
- `reflex_and_admit` with deterministic `interrupt` and
  `current_interaction` scope;
- no ordinary Core planning for the stop turn;
- a trusted cancelled Soridormi result rather than inferred cancellation;
- endpoint-reported source identity and the same runtime-identity digest;
- explicit safe idle before the request and after cancellation.

The observation contains request identity, named skill, Provider identity, Goal
ownership, and started/done state only. It excludes arguments and Provider
payloads and does not authorize cancellation.

## Retained MuJoCo case

The maintained compound request runs through the same Goal-Driven Runtime and
trusted Skill Runtime to Soridormi. Qualification requires:

- cognitive runtime mode `apply` on the `robot_action` lane;
- the exact evaluated Chromie revision;
- a clean declared paired Soridormi checkout;
- an endpoint-reported Soridormi revision matching that checkout;
- the same retained runtime identity used by the live-text run;
- at least the declared walk, nod, and turn terminal skills;
- completed Soridormi `sim` results;
- explicit safe idle before and after execution.

A provider revision declared only by the local capability manifest is not enough.
The running Soridormi endpoint must report its own source revision.

## Fail-fast deployment preflight

Before identity capture or any retained model/MuJoCo case, the workflow runs a
read-only deployment preflight. It requires:

- clean committed Chromie and Soridormi worktrees;
- the Chromie capability manifest upstream revision to match the paired
  Soridormi checkout;
- a healthy Chromie Agent that loaded the Soridormi capability source;
- the running Soridormi endpoint to report `sim`, no active task, no emergency
  stop, no fallen state, and `safe_idle=true`;
- `robot.get_status` to report its own source/provider revision;
- that endpoint revision to match both the paired checkout and the Chromie
  capability manifest.

The preflight sends no user utterance and executes no motion. Missing or
mismatched endpoint identity fails before any expensive evidence stage starts.
Its retained `preflight.json` is diagnostic readiness evidence only and cannot
make the Issue closure-eligible or release-qualified. Run it independently with:

```bash
python scripts/preflight_cognitive_gateway_core_qualification.py \
  --soridormi-repo ../soridormi \
  --output .chromie/acceptance/cognitive-gateway-core/preflight.json
```

## Run the qualification

The maintained entrypoint is a single resumable workflow. It runs the fail-fast
preflight first, then coordinates the existing collectors and verifier without
injecting expectations into cognition:

```bash
python scripts/run_cognitive_gateway_core_qualification.py collect \
  --reviewer "<reviewer identity>" \
  --soridormi-repo ../soridormi
```

The command creates a timestamped evidence root under
`.chromie/acceptance/cognitive-gateway-core/`, records each exact subprocess and
log, and fingerprints every expected artifact in `workflow-state.json`. If an
environmental interruption occurs, resume the same root only after correcting the
external problem:

```bash
python scripts/run_cognitive_gateway_core_qualification.py collect \
  --reviewer "<reviewer identity>" \
  --soridormi-repo ../soridormi \
  --evidence-root "${EVIDENCE_ROOT}" \
  --resume

python scripts/run_cognitive_gateway_core_qualification.py status \
  --evidence-root "${EVIDENCE_ROOT}"
```

Resume skips a stage only when the state says it completed and every retained
artifact still matches its SHA-256 fingerprint. The workflow reads the active
cancellation command, interrupt text, and required Provider skill from the
versioned qualification manifest. It does not contain a second copy of those
semantic inputs.

After reviewing the artifacts, explicitly edit the generated
`human-review.json`; every required check remains `pending` until a human changes
it. Finalize the exact bundle with:

```bash
python scripts/run_cognitive_gateway_core_qualification.py finalize \
  --evidence-root "${EVIDENCE_ROOT}"
```

`finalize` delegates to the fail-closed verifier and exits successfully only when
that report says `issue_closure_eligible=true`. It can never set
`release_qualified=true`. The expanded commands below remain documented for
diagnostics and individual-stage reruns.

Apply, test, commit, and push the implementation before collecting evidence.
The identity capture rejects a dirty checkout.

Start Soridormi/MuJoCo from the clean paired revision. Then start Chromie's
service containers without a second Host Orchestrator:

```bash
./scripts/start_chromie.sh \
  --build \
  --no-orchestrator \
  --keep-services
```

Create one evidence directory and capture the exact running identity:

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_ROOT=".chromie/acceptance/cognitive-gateway-core/${RUN_ID}"
mkdir -p "${EVIDENCE_ROOT}"

python scripts/capture_runtime_identity.py \
  --compose-override .chromie/voice-runtime/compose.voice-mujoco.yaml \
  --orchestrator-env .chromie/voice-runtime/orchestrator.env \
  --output "${EVIDENCE_ROOT}/runtime-identity.json"
```

Run the maintained live-service text cases:

```bash
python scripts/cognitive_gateway_core_live_text.py \
  --runtime-identity "${EVIDENCE_ROOT}/runtime-identity.json" \
  --output-dir "${EVIDENCE_ROOT}/live-text" \
  --no-speaker
```

Run the compound text-to-MuJoCo case:

```bash
python scripts/interaction_text_mujoco_check.py \
  --runtime-identity "${EVIDENCE_ROOT}/runtime-identity.json" \
  --soridormi-repo ../soridormi \
  --evidence-dir "${EVIDENCE_ROOT}/mujoco" \
  --no-speaker \
  --expect-route robot_action \
  --expect-skill soridormi.walk_velocity \
  --expect-skill soridormi.nod_yes \
  --expect-skill soridormi.turn_in_place \
  --reject-internal-speech
```

Run active-Goal cancellation with the exact manifest-owned texts:

```bash
python scripts/interaction_text_mujoco_check.py \
  "Walk forward at 0.2 meters per second for 20 seconds." \
  --runtime-identity "${EVIDENCE_ROOT}/runtime-identity.json" \
  --soridormi-repo ../soridormi \
  --evidence-dir "${EVIDENCE_ROOT}/active-cancel" \
  --no-speaker \
  --expect-route robot_action \
  --interrupt-text "Stop." \
  --interrupt-skill-prefix soridormi.walk_velocity \
  --expect-cancelled \
  --reject-internal-speech
```

Create a fingerprint-bound review template after inspecting the retained
responses, traces, cancellation timing, and simulator behavior:

```bash
python scripts/create_cognitive_gateway_core_review.py \
  --runtime-identity "${EVIDENCE_ROOT}/runtime-identity.json" \
  --live-summary "${EVIDENCE_ROOT}/live-text/summary.json" \
  --mujoco-summary "${EVIDENCE_ROOT}/mujoco/summary.json" \
  --cancellation-summary "${EVIDENCE_ROOT}/active-cancel/summary.json" \
  --reviewer "<reviewer identity>" \
  --output "${EVIDENCE_ROOT}/human-review.json"
```

The generated record is deliberately `pending`. The reviewer must set every
required qualitative check to `pass` and set `decision` to `approve`; the
verifier rejects stale or substituted artifact fingerprints.

Verify the complete bundle:

```bash
python scripts/verify_cognitive_gateway_core_qualification.py \
  --runtime-identity "${EVIDENCE_ROOT}/runtime-identity.json" \
  --live-summary "${EVIDENCE_ROOT}/live-text/summary.json" \
  --mujoco-summary "${EVIDENCE_ROOT}/mujoco/summary.json" \
  --cancellation-summary "${EVIDENCE_ROOT}/active-cancel/summary.json" \
  --human-review "${EVIDENCE_ROOT}/human-review.json" \
  --output "${EVIDENCE_ROOT}/qualification.json"
```

The report always retains:

```json
{
  "release_qualified": false,
  "human_review_required": true
}
```

`issue_closure_eligible=true` now means the live-text, normal MuJoCo, active-Goal
cancellation, identity/provenance, safe-idle, and fingerprint-bound human-review
contracts all passed. It remains a project-Issue closure signal, not release
qualification.

## Failure handling

Failures are classified at the earliest evidence boundary:

- identity capture: dirty source, missing image, runtime fingerprint drift, or
  launcher/model mismatch;
- Gateway evidence: wrong admission, stale attention context, reflex mismatch, or
  admitted ambient speech;
- Core evidence: missing single-authority result, wrong lane, missing Goal
  continuity, or repeated tool lookup;
- execution evidence: missing outcome bundle, unexpected named skills, Provider
  refusal/failure, or incomplete result;
- provenance: mismatched Chromie/Soridormi revision or missing endpoint revision;
- simulator safety: wrong backend/mode or missing explicit pre/post safe idle;
- cancellation: interrupt before Provider start, missing Goal binding, wrong
  scope, inferred cancellation, or missing post-cancel safe idle;
- human review: stale artifact digest, incomplete qualitative checks, or a
  non-approved decision.

A failed run is retained as evidence. It must not be repaired by adding phrase
rules, scenario branches, fixed outputs, or Benchmark-authored Runtime policy.
