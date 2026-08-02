# Scenario Candidate Data Loop

## Purpose

Offline scenario mining converts episode evaluations into durable, correlated
scenario-candidate events. A candidate is a proposal for human review. It is not an
active regression scenario, training sample, prompt update, or runtime policy.

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
`conversation_id` when available. This allows the external data loop to retain,
merge for transport, and later query all evidence associated with a candidate.

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
