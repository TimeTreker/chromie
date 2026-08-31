# Chromie Latest Handoff

Audience: coding agent or operator reviewing Issue #33 or resuming provider qualification.
Owner: project owner. Replace this snapshot when `DEVELOPMENT_CHECKPOINT.md` advances.
Authority: operational snapshot only; current source, tests, retained evidence, and the
checkpoint win.

## Repository state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Issue: [#33 — Customer-configurable Stable Mind personalization](https://github.com/TimeTreker/chromie/issues/33)
- Delivery branch: `codex/customer-mind-personalization`
- Pre-delivery base: `main` at `7596ee06f693b08918fde99063fbf24018a4e2dc`
- Expected resume revision: latest
  `origin/codex/customer-mind-personalization` commit containing this handoff and
  `DEVELOPMENT_CHECKPOINT.md`
- Delivery scope: bounded customer identity/worldview/value/social-style configuration,
  shared prompt projection, runtime selection, executable CLI, tests, and owned docs
- Owner authorization: explicit exception to the current qualification-only delivery line
- No force push, deployment, profile activation, release, or external customer operation
  is part of this delivery

## Stable Mind authority flow

```text
config/mind/chromie_default.json (factory authority)
  + CustomerMindPersonalization (bounded owner-confirmed input)
  -> apply_customer_mind_personalization()
  -> complete .chromie/mind/active_profile.json
  -> validate_customer_mind_profile() exact factory-derived comparison
  -> Host/Agent MindProfile
  -> bounded stable projection
       -> Fast Planner
       -> Deep Planner
       -> Selective Reflection
```

One Stable Mind owner supplies all model roles. The customer input does not become a raw
system prompt and cannot create independent per-model identities or values.

## Delivered changes

- Added independent typed `Worldview`, `HouseholdValues`, and
  `CustomerMindPersonalization` sections to `shared/chromie_contracts/mind.py`.
- Added deterministic profile derivation and strict current-factory validation. A customer
  profile is valid only when every field exactly equals the recomputed allowed result.
- Allowed only display name, pronouns, family role, reviewed social-style preset, at most
  eight worldview perspectives, and at most eight household values.
- Preserved protected factory/core authority: safety, privacy, consent, truthfulness,
  embodiment, current evidence for changing facts, and current user intent cannot be
  overridden by customer values or preferences.
- Added automatic active-profile selection in Host settings and Agent mind loading only
  when `ORCH_MIND_PROFILE_PATH` is not explicit. Existing explicit-path authority remains.
- Added one bounded Stable Mind projection to Fast Planner, Deep Planner, and Selective
  Reflection. Active configured name/role facts take precedence over factory display-name
  wording; factory identity category remains fixed.
- Added `scripts/configure_chromie_mind.py`: preview by default, atomic `--apply`, private
  mode `0600`, customer-version increment, backup before replacement, and recoverable
  `--reset`.
- Updated the factory profile to version `0.7.0` and updated existing configuration, mind,
  status, and user-manual owners. No new standalone design document was added.
- Added focused contract, prompt-propagation, CLI, permission, auto-selection, and reset
  tests.

Repository surface delta: two new tracked files (configuration CLI and focused test),
17 modified existing implementation/config/test/document/handoff owners after this handoff
pair is included. New current documents, environment variables, runtime switches,
architecture terms, compatibility paths, provider profiles, and model authorities: zero.
The new executable boundary and its test have no equivalent owner suitable for consolidation.

## Runtime and profile identity

- Factory profile: `config/mind/chromie_default.json`
- Factory profile id/version: `chromie_default_mind` / `0.7.0`
- Factory file SHA-256 observed before commit:
  `5a4c937f204fd1294ce2a41ebe0b1a47540f1c6b24adae6366e05d141ebce321`
- Default customer profile path: `.chromie/mind/active_profile.json`
- Customer preview id/version observed:
  `chromie_default_mind.customer` / `0.7.0+customer.1`
- Active customer profile at delivery time: absent; preview did not write it
- Explicit `ORCH_MIND_PROFILE_PATH`: unchanged and still takes precedence
- Deployed Agent/Host/model/profile identity for Issue #33: not run / unknown

## Exact commands and observed evidence

Focused regression:

```text
python -m pytest tests/test_mind_profile.py tests/test_cognitive_identity_context.py tests/test_configure_chromie_mind.py
28 passed in 0.51s
```

Preview probe:

```bash
python scripts/configure_chromie_mind.py \
  --name Nova \
  --family-role "our household helper" \
  --social-style neutral \
  --worldview-perspective "Learning is something the household does together." \
  --household-value "Prefer calm explanations."
```

Observed: status `preview`, profile id `chromie_default_mind.customer`, version
`0.7.0+customer.1`, expected bounded values, and no active profile written.

Canonical local evidence:

```text
python scripts/check_repository_policies.py
15 rule families, 0 reviewed exceptions; passed

./scripts/run_tests.sh
2,051 main tests in 26.259s; OK
20 legacy Agent tests passed
Pinned test-ownership and static-analysis checks passed within the gate

python scripts/check_docs.py
98 Markdown files; passed

git diff --check
passed
```

The full gate logs contain expected negative-fixture and fault-injection warnings/errors;
the command exited zero. No failing required local check is known.

## Retained evidence and unavailable evidence

- No new feature-specific acceptance bundle or generated profile is retained.
- The CLI preview wrote no file. Apply/reset behavior was exercised only in isolated
  temporary test directories, which were removed by the tests.
- Existing ignored `.chromie/acceptance/` artifacts belong to earlier GI qualification
  work and are not evidence for Issue #33.
- Live service restart, deployed-model outputs, GUI behavior, household authorization,
  audible voice, microphone, simulator, target hardware, physical safety, and release
  evidence are unavailable and must not be inferred from the local tests.

## Review and resume commands

```bash
git fetch origin codex/customer-mind-personalization
git switch codex/customer-mind-personalization
git pull --ff-only origin codex/customer-mind-personalization
git show --stat --oneline HEAD
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

For a non-persistent review, run the preview probe above. Do not add `--apply` on a real
household system until the owner has reviewed the values and a recoverable backup location.

The next Issue #33 product step is an authenticated customer onboarding/settings surface
that calls the same derivation/validation boundary and preserves preview, explicit owner
confirmation, private storage, versioning, and reset recovery. Before any customer-visible
claim, qualify one active profile through an exact deployed model and real service restart,
retain both factory/customer digests and runtime identity, and inspect the role-consistency
output. Then return to the pre-existing provider/live/target-evidence delivery line.

## Claim boundary

Source implementation and automated local evidence only. The branch provides a real
operator/customer CLI and runtime contract, but no deployed service, authenticated GUI,
live model behavior, audible voice, robot, target hardware, or release qualification.
