# Target Evidence Closure

Status: current target-evidence coordination authority

Chromie's named implementation backlog is complete. This workflow coordinates
retained evidence for the current committed source without adding cognition,
changing Runtime policy, approving human review, or declaring release readiness.

The governing manifest is:

```text
benchmarks/manifests/target_evidence_closure_v1.json
```

The coordinator is:

```text
scripts/run_target_evidence_closure.py
```

Every report remains source-bound, fingerprinted, and explicit about its claim.
The coordinator independently verifies that every retained track belongs to the
exact clean Chromie revision recorded by `init`; an eligible report from another
revision cannot be mixed into the closure. A completed closure report always
contains `release_qualified=false`; product or physical release approval remains
a separate owner decision.

The strict current-revision `speech-only` verifier is implemented, but physical
target validation is deferred because the current host has no microphone. That
does not weaken the physical claim and does not block `source_bound_development`,
whose required tracks are non-physical. It remains required for
`supervised_physical_pilot` and does not satisfy Gateway/Core MuJoCo, Agent
Skill/weather, Social Attention, LAN, or physical-robot tracks.

## Profiles

### `source_bound_development`

Required tracks:

- Cognitive Gateway/Core live text, cancellation, paired MuJoCo, and approved
  source-bound review;
- positive live Agent Skill selection plus provider-backed weather execution;
- the complete homogeneous Social Attention baseline plus approved qualitative
  review;
- loopback-local and second-machine LAN exposure evidence.

Physical voice and physical robot evidence are optional and do not affect this
profile's development closure claim.

### `supervised_physical_pilot`

Requires every source-bound development track plus:

- supervised physical microphone/speaker evidence;
- supervised physical robot execution with a safety operator, verified stop
  path, bounded workspace, provider source identity, and post-execution safe
  state.

Simulation, virtual audio, or operator-free execution cannot satisfy this
profile.

## Initialize one closure

Start from clean committed Chromie and paired Soridormi checkouts with the
maintained services and Soridormi `sim` endpoint running:

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_ROOT=".chromie/acceptance/target-evidence/${RUN_ID}"

python scripts/run_target_evidence_closure.py init \
  --profile source_bound_development \
  --reviewer "$USER" \
  --evidence-root "$EVIDENCE_ROOT"
```

Use the stricter profile only when supervised physical evidence is intended:

```bash
python scripts/run_target_evidence_closure.py init \
  --profile supervised_physical_pilot \
  --reviewer "$USER" \
  --evidence-root "$EVIDENCE_ROOT"
```

## Revision lifecycle

Initialize a closure only after the code and configuration under qualification
have been committed. Collection, attachment, and track finalization fail closed
when the checkout is dirty or no longer matches the revision captured by
`init`. If a defect is fixed after evidence collection begins, commit the fix
and create a new evidence root; do not carry reports or approvals forward from
the earlier revision.

The `status` command may still inspect an existing bundle from another checkout,
but that does not make its reports eligible for the current revision.

## Gateway/Core source-bound evidence

```bash
python scripts/run_target_evidence_closure.py collect-core \
  --evidence-root "$EVIDENCE_ROOT" \
  --soridormi-repo ../soridormi \
  --agent-url http://127.0.0.1:8092 \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
```

Before retained cognition or motion, the Core collector binds the generated
Orchestrator environment and requires a complete no-playback synthesis from its
selected TTS. Manifest-declared speech turns then require correlated completed
delivery; scheduled, skipped, failed, or undelivered speech cannot satisfy the
track.

Review the exact artifacts and edit:

```text
$EVIDENCE_ROOT/gateway-core/human-review.json
```

Only then finalize:

```bash
python scripts/run_target_evidence_closure.py finalize-core \
  --evidence-root "$EVIDENCE_ROOT"
```

The specialized procedure remains documented in
[Gateway/Core Source-Bound Qualification](COGNITIVE_GATEWAY_CORE_QUALIFICATION.md).

## Agent Skill and provider-backed weather evidence

This track reuses the exact Gateway/Core runtime identity. It proves live
selection of both approved methods, content-free Plan provenance, correct
Neixiang discourse grounding, provider-backed `chromie.weather.lookup`
evidence, and exact verified-memory reuse on the follow-up. The retained
execution evidence separately proves that the canonical request remains
`河南省内乡县` while the Open-Meteo adapter uses its provider-native lookup key
`neixiang`; provider syntax never replaces the Goal binding.

```bash
python scripts/run_target_evidence_closure.py collect-skill-weather \
  --evidence-root "$EVIDENCE_ROOT" \
  --agent-url http://127.0.0.1:8092
```

Review and approve:

```text
$EVIDENCE_ROOT/agent-skill-weather/human-review.json
```

Then:

```bash
python scripts/run_target_evidence_closure.py finalize-skill-weather \
  --evidence-root "$EVIDENCE_ROOT"
```

The verifier rejects missing Skill provenance, digest drift, stale/mismatched
Goal bindings, canonical-location rewriting, an unexpected provider lookup key,
a wrong administrative match, repeated lookup on the exact-memory follow-up,
or a Chongqing observation used to answer the corrected Neixiang request. Every
manifest-declared runtime turn must retain an applied terminal event. Every
fresh weather read, including one represented by a `mixed` Plan, must also retain
a successful model-owned pre-evidence speech review. This is evidence that the
semantic boundary ran, not a Host wording classifier; the fingerprint-bound
human review still judges the actual speech.
Before planning, Goal Association also rejects a new direct location binding
that is not grounded as a contiguous verbatim span of the authoritative current
turn; indirect references remain eligible only through their supplied referent
provenance. One bounded model repair may correct the DTO, otherwise the turn
fails closed. Provider aliases never repair this semantic boundary.
A material correction to an external-read binding requires a new exact read
when the corrected answer still depends on external facts. A
capability-dependent direct response is valid without retrieval only when the
supplied delivered evidence-bound dialogue names that same Goal; a result for a
different entity or Goal cannot be relabelled.

## Social Attention baseline

Configure the first-party deployed-service adapter before collection, for
example:

```bash
export CHROMIE_BENCHMARK_LIVE_SERVICE_CALLABLE=qualification_harness.live_service:invoke
```

Collect all reviewed launcher-effective mode/style slices and build the hard-gate
qualification report in one command:

```bash
python scripts/run_target_evidence_closure.py collect-social \
  --evidence-root "$EVIDENCE_ROOT" \
  --prompt-revision <prompt-revision> \
  --provider-revision <provider-revision> \
  --hardware-profile <hardware-profile> \
  --mind-profile <approved-mind-profile-revision> \
  --runtime-topology cognitive-runtime-apply \
  --effective-model response_composer=<resolved-model> \
  --effective-model social_attention=<resolved-model>
```

The collector derives the complete mode/style set from the reviewed dataset,
runs each slice independently, and assembles the qualification report. Review
qualitative samples and edit:

```text
$EVIDENCE_ROOT/social-attention/human-review.json
```

An externally generated source-bound qualification may instead be attached:

```bash
python scripts/run_target_evidence_closure.py attach-social \
  --evidence-root "$EVIDENCE_ROOT" \
  --qualification <qualification.json> \
  --review <approved-review.json>
```

Benchmark remains an evaluator. It does not choose Social Attention behavior for
the Runtime.

## Deployed loopback and LAN evidence

On the Chromie host, after all maintained services are running:

```bash
python scripts/runtime_exposure_evidence.py local \
  --target-host <chromie-lan-address> \
  --output "$EVIDENCE_ROOT/lan-local.json"
```

On a second machine on the same LAN, copy only
`scripts/runtime_exposure_evidence.py` and run:

```bash
python runtime_exposure_evidence.py remote \
  --target-host <chromie-lan-address> \
  --control-host <chromie-lan-address> \
  --control-port 22 \
  --output lan-remote.json
```

The reachable control port proves that the observer actually has a LAN path.
The four internal Chromie ports must remain unreachable. Copy the remote report
back and attach both:

```bash
python scripts/run_target_evidence_closure.py attach-lan \
  --evidence-root "$EVIDENCE_ROOT" \
  --local-report "$EVIDENCE_ROOT/lan-local.json" \
  --remote-report <lan-remote.json>
```

## Optional physical voice evidence

Collect supervised physical voice evidence through the maintained voice tool:

```bash
python scripts/voice_acceptance.py --mode supervised --operator "$USER"
```

Attach the resulting evidence directory:

```bash
python scripts/run_target_evidence_closure.py attach-voice \
  --evidence-root "$EVIDENCE_ROOT" \
  --evidence-dir <voice-evidence-directory>
```

Physical microphone accuracy and listening quality require human review; virtual
or synthetic audio cannot substitute for them.

## Optional physical robot evidence

Physical robot evidence is never collected automatically by the closure tool.
The supervised report must contain:

```json
{
  "evidence_type": "physical_robot_supervised",
  "passed": true,
  "physical_robot_claim_eligible": true,
  "chromie_revision": "<exact revision>",
  "source_clean": true,
  "provider_source_bound": true,
  "safe_state_before": true,
  "safe_state_after": true,
  "operator": "<safety operator>"
}
```

Attach it with its approved fingerprint-bound review:

```bash
python scripts/run_target_evidence_closure.py attach-physical-robot \
  --evidence-root "$EVIDENCE_ROOT" \
  --qualification <physical-robot-qualification.json> \
  --review <approved-review.json>
```

Follow Soridormi's commissioned-hardware stop and recovery procedure throughout.

## Status and finalization

```bash
python scripts/run_target_evidence_closure.py status \
  --evidence-root "$EVIDENCE_ROOT"

python scripts/run_target_evidence_closure.py finalize \
  --evidence-root "$EVIDENCE_ROOT"
```

Finalization fails when the checkout moved, became dirty, a report is missing,
a human review is pending or stale, or any required track does not claim its
exact reviewed eligibility state.

The final report is:

```text
$EVIDENCE_ROOT/closure-report.json
```

A successful default closure supports only this claim:

> The evaluated committed development revision has complete source-bound
> Gateway/Core, Agent Skill/weather, Social Attention, and LAN-exposure evidence
> with the required human reviews.

It does not claim physical-device support or release qualification.
