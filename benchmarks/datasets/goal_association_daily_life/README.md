# Goal Association Daily-Life Corpus

Audience: GA reference authors and qualification operators. Separate scenario JSON
and `dataset.json` own frozen inputs, coverage, split membership and asset identity.
Issue [#34](https://github.com/TimeTreker/chromie/issues/34) identifies the original
corpus work; current Issue disposition was not rechecked by this local audit.

## Inventory and current compatibility

The retained 1,500 cases are 100 bilingual semantic seeds with 15 Goal-continuity
contrasts each. They cover creation, continuation, modification, clarification,
confirmation, rejection, cancellation, pause/resume, terminal reference, replacement,
unrelated work, merge/split and mixed continuity/new work.

GA owns Goal identity and relationships. Its primary collections are
`associations` and `new_goals`. Each new-Goal row contains exactly the accepted UMI
source ref, `related_goal_ids`, and `supersedes_goal_ids`; Host inherits complete
WHAT from UMI and copies GA relationships unchanged. Related IDs may include
terminal history; only open supplied Goals can be superseded. Both collections
can occur in one result. Neither GA nor Host adds a missing UMI Planner request.

The 2026-10-04 relationship repair replaces the incomplete unassociated-ref-only
wire with this existing identity/relationship API. The 1,300 link-free references
regain explicit empty relationship arrays; the 200 linked references retain their
original choices. Empty retired non-goal fields are removed. Original input, WHAT,
candidates, oracle maps, confidence, cognition requests, ordering, contrasts and
splits are unchanged. Before-bytes and per-file proofs are retained under
`.chromie/acceptance/ga-relationship-contract-20261004T111406Z/`.

The first complete baseline accepted 1,090 through Host, retained 200 typed-state
negatives and reported 210 errors. Restoring GA relationships raised mechanical
Host acceptance to 1,280 with 20 remaining media failures. GA's wrong requirement
for a pre-extracted UMI media operation was then removed: complete media intention
is handed to Planner for argument extraction. The final cohort and gate logs are
retained in that evidence root. Typed-state negatives remain fail closed without
state leakage; they are not successful fulfillment.

Fifty historical-restatement inputs still carry the old body's/state's/media's
result type. Their accepted WHAT is preserved, rather than corrected by GA; they
need upstream fixture review. Mechanical validity does not make them independently
reviewed semantic targets or native-model qualification.

Validation now captures the exact production primary Schema and checks Host
materialization against the full responsibility map, including related and
superseding identities. Qualification can capture a permitted fail-closed reference's
primary call; it does not treat that refusal as fulfillment. A regression rejects
Schema-valid/Host-resolved output that loses a referenced historical identity.

## Validation and frozen migration

```bash
python benchmarks/datasets/goal_association_daily_life/validate.py
```

Keep the validator strict. Migrate at the reference/transaction owner after review,
retaining original turns, accepted UMI provenance, retained Goal snapshots, 15-member
contrasts and splits. Do not restore retired model fields or auto-author targets from candidate output. Refreeze source and case
digests only after reviewed migration; preserve original failures and identities.

Every case remains `training_eligible=false`. A valid JSON/DTO is not independent
semantic, native-model, Agent HTTP, voice, simulator or robot evidence.
The old qualification replay failures occur before such claims can be made.
Use the [project qualification method](../../../docs/LLM_PROMPT_QUALIFICATION_METHOD.md)
and [audit](../../../ARCHITECTURE_AUDIT.md) before preparing new target-blind cohorts.
The manifest binds the reconciled scenario digest. Linked-reference contract changes
require owner authorization; never erase the original relationship to obtain a pass.
