# Cognitive Gateway/Core Source-Bound Qualification

Status: maintained qualification procedure for the active Gateway/Core migration Issue.

This procedure validates the implemented interaction authority boundary against
running services and Soridormi/MuJoCo. It does not add cognition, infer expected
intent from user text, select a model, or grant release readiness.

## Qualification claim

A passing bundle may support this narrow claim:

> The evaluated Chromie revision admitted or suppressed each retained turn at the
> Cognitive Gateway before ordinary semantic interpretation, used the Goal-Driven
> Cognitive Core as the single semantic authority for admitted turns, preserved
> trusted tool evidence across a follow-up, executed the retained compound body
> request through the evaluated Soridormi `sim` endpoint, and returned to an
> explicitly reported safe-idle state.

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
only and cannot qualify the Issue.

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

## Run the qualification

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

Verify the complete bundle:

```bash
python scripts/verify_cognitive_gateway_core_qualification.py \
  --runtime-identity "${EVIDENCE_ROOT}/runtime-identity.json" \
  --live-summary "${EVIDENCE_ROOT}/live-text/summary.json" \
  --mujoco-summary "${EVIDENCE_ROOT}/mujoco/summary.json" \
  --output "${EVIDENCE_ROOT}/qualification.json"
```

The report always retains:

```json
{
  "release_qualified": false,
  "human_review_required": true
}
```

`issue_closure_eligible=true` means the automatic evidence contracts passed. It
still requires review of the retained responses, traces, source identities, and
provider behavior before closing the Issue.

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
- simulator safety: wrong backend/mode or missing explicit pre/post safe idle.

A failed run is retained as evidence. It must not be repaired by adding phrase
rules, scenario branches, fixed outputs, or Benchmark-authored Runtime policy.
