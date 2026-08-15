# Chromie Data Loop: Interaction Evidence and Scenario Candidates

## Purpose

Offline scenario mining converts episode evaluations into durable, correlated
scenario-candidate events. A candidate is a proposal for human review. It is not an
active regression scenario, training sample, prompt update, or runtime policy.

This document also owns Chromie's current interaction-Session fact-layer
collection policy. Its audience is runtime, data-governance, and evaluation
maintainers. The policy belongs here because scenario candidates are downstream
derivations of the retained Session evidence; a separate design document would
split one provenance chain across competing owners.

## Architecture baseline

Chromie follows `TimeTreker/nozdormu` v1.x as the current approved architecture
baseline. `CP-2026-001` and its v2 registry drafts inform the replaceable Policy
Provider, logical-demand/physical-artifact separation, and usage-provenance
direction, but they are proposed material and are not frozen Chromie contracts.

The maintained boundary is:

- Chromie Session lifecycle owns the domain trigger meaning;
- the typed Policy Provider supplies a versioned effective snapshot;
- the validated input buffer, RuntimeTrace, and EpisodeRecorder are Evidence
  Providers, not business-semantic authorities;
- compatible demands may reference or hard-link the same immutable bytes when
  governance permits, without merging purpose, retention, or provenance;
- the generic Runtime Event/Data Loop boundary transports completed packages but
  does not decide why a Session should be captured.

## Interaction-Session capture policy

`chromie.interaction_session_capture` is one independently controlled Data Loop
policy. It is not a global Data Loop enable switch and does not control trace
sampling, episode recording, scenario mining, incident retention, or aggregate
telemetry. The current local provider reads the file selected by
`ORCH_DATA_LOOP_INTERACTION_SESSION_CAPTURE_POLICY_PATH`; an unset path resolves
to a typed disabled snapshot. The maintained example is
[`config/data_loop/interaction_session_capture.example.json`](../config/data_loop/interaction_session_capture.example.json).

The provider resolves exactly once when `SessionTracker` starts one SID. A file
refresh during that SID cannot mutate its snapshot. The next SID receives the
new version. A later signed/cloud-cached provider can implement the same typed
interface without changing VAD, Session, Recorder, trace, or Episode lifecycle
code.

```text
session_start
→ resolve and snapshot policy ID/version/config
→ reuse the validated VAD input buffer when audio is requested
→ normal ASR/Gateway/Core/Goal/Plan/Runtime/TTS/Playback
→ session_complete or session_abandoned
→ finalize RuntimeTrace
→ seal one immutable interaction-Session evidence event
→ notify the external Data Loop when its inbox is configured
```

No quality-evaluation LLM or scenario miner runs on this realtime path.

### Fact-layer package

One enabled activation produces
`chromie.interaction_session_evidence/session_complete` or
`session_abandoned`. The package is a manifest plus separate immutable
artifacts, not one giant JSON document:

```text
event.json
interaction-session-evidence.json
input-audio.pcm16             # only when requested and captured
runtime-trace.json
trace-summary.json
episode.json
```

The evidence manifest records SID, start/end time, termination state,
conversation/Episode/trace IDs, exact policy snapshot and digest, runtime/profile
identity, artifact IDs/digests/sizes, and explicit missing/partial status.
Completion, abandonment, timeout, shutdown, and restart recovery use the same
deterministic policy-activation/event identity, so retry cannot commit a second
effective result. Restart recovery never invents a missing Episode or trace; it
seals the available evidence as partial.

### Audio privacy and governance

Data Loop input audio is retained only when the effective policy requests
`evidence.user_input_audio=true`. It reuses the exact validated mono PCM16 buffer
already handed to ASR and does not create a second microphone framework.
`ORCH_SAVE_AUDIO` remains an independent operator/debug feature: enabling it does
not create Data Loop evidence, and disabling it does not defeat an explicitly
enabled Data Loop policy.

Raw speech, transcripts, Episodes, traces, and runtime identities can contain
personal or deployment-sensitive data. Operators must review the policy's
`usage_purpose` and `retention_profile_id`, filesystem access, trigger target,
upload destination, and deletion process before enabling it. A local trigger
file proves only local handoff; it is not proof of cloud upload, retention
enforcement, consent, anonymization, or deletion. Evidence immutability applies while
an artifact is retained; authorized retention/privacy deletion is allowed and need not
leave a universal tombstone. After deletion, downstream evaluation must treat missing
coverage as unknown rather than infer that the deleted event never occurred.

## Derivation chain

```text
runtime incident ─┐
                  ├─ correlation and offline analysis
experience episode┘
                         ↓
                  episode evaluation
                         ↓
                scenario candidate event
                         ↓
                     human review
                    ↙            ↘
                reject          approve
                                  ↓
                    separate promotion workflow
                    ↙                         ↘
             regression scenario          curated training data
```

Original incidents, Runtime Traces, and episodes remain immutable evidence. The
scenario candidate is a separate derived artifact and references its source IDs.
Runtime Trace contributes execution topology and latency, while the Episode
contributes semantic history. See
[Runtime Observability Architecture](RUNTIME_OBSERVABILITY.md).

When the source Episode came from an enabled interaction-Session capture policy,
its metadata carries the deterministic source SID, evidence-event ID, policy
activation ID, policy ID/version, and policy digest. Candidate review metadata
and Runtime Event correlations preserve that reference, allowing an auditor to
resolve the exact input audio, RuntimeTrace, Episode, runtime revision/profile,
and governing policy snapshot without copying fact-layer semantics into the
candidate.

## Runtime event

Candidate events use:

```text
event_type    = chromie.scenario_candidate
event_subtype = experience_mined
producer      = chromie.experience_evaluator
```

The event package contains:

```text
event.json
scenario_candidate.json
source_episode.json
source_evaluation.json
```

Correlation metadata includes `scenario_id`, `episode_id`, `evaluation_id`, and
`conversation_id` when available. Policy-captured sources additionally include
`source_session_id`, `interaction_session_evidence_event_id`,
`data_loop_policy_id`, and `data_loop_policy_version`. This allows the external
data loop to retain, merge for transport, and later query all evidence associated
with a candidate.

## Mandatory review gate

Every newly mined candidate must declare:

```json
{
  "review": {
    "status": "pending_human_review",
    "requires_human_review": true
  },
  "promotion": {
    "regression_allowed": false,
    "training_allowed": false,
    "auto_promotion_allowed": false,
    "required_review_status": "approved"
  }
}
```

The candidate event producer rejects any unreviewed candidate that already
allows regression or training promotion. Approval and promotion are intentionally separate from the mining command. The
implemented Benchmark workflow writes a review record bound to the immutable
candidate fingerprint and promotes only an approved candidate through a separate
auditable command.

## Command

Existing candidate file generation remains supported. Runtime event emission is
optional:

```bash
python scripts/evaluate_experience_episodes.py \
  --candidate-dir .chromie/experience/candidates \
  --emit-candidate-events \
  --runtime-event-root /var/lib/chromie/runtime-events \
  --data-loop-trigger-root /var/lib/data-loop/inbox
```

The root options override the equivalent environment variables. When event
emission is disabled, the existing timestamped candidate JSON files are still
written exactly as before, with the additional review and promotion metadata.

## Data-loop boundary

Chromie owns candidate derivation, evidence packaging, correlation IDs, and the
review gate. The external data loop owns event uniqueness, transport merging,
bandwidth and storage control, upload reliability, retention, and cloud delivery.

Cloud analysis may rank, cluster, or annotate candidates, but it must not mutate
the immutable source package or silently promote a candidate.

## Implemented review and promotion workflow

```bash
python -m benchmarks.mining index \
  --candidate-dir .chromie/scenario_candidates \
  --output .chromie/benchmark-artifacts/candidate_catalog.json

python -m benchmarks.mining review candidate.json \
  --decision approved --reviewer owner-id \
  --rationale "Reproduces the earliest wrong boundary." \
  --output candidate.review.json

python -m benchmarks.mining promote candidate.json \
  --review candidate.review.json --id reviewed_regression_case
```

The candidate remains immutable and pending review. Approval lives in a separate
record containing its SHA-256 fingerprint. Promotion rejects exact duplicates,
requires explicit reviewer acknowledgement for related committed scenarios,
validates the deterministic scenario contract, and preserves source provenance.
It never commits changes or edits Prompts, personality, safety, or Runtime policy.
