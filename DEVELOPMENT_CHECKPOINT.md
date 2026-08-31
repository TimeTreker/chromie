# Chromie Development Checkpoint

Status: Issue #33 customer-configurable Stable Mind source implementation complete; customer UI/authentication and deployed-model qualification remain open
Updated: 2026-08-31
Pre-delivery baseline: `main` at `7596ee06f693b08918fde99063fbf24018a4e2dc`
Expected resume revision: latest `origin/codex/customer-mind-personalization` commit containing this checkpoint and `HANDOFF.md`

## Read first

Read [Project Charter](docs/PROJECT_CHARTER.md),
[Human-Like Interaction Contract](docs/HUMAN_LIKE_INTERACTION_CONTRACT.md),
[Current Status](docs/STATUS.md), [Roadmap](ROADMAP.md),
[Acceptance](docs/ACCEPTANCE.md), and [Latest Handoff](HANDOFF.md).
Current source, tests, and retained executable evidence win.

## Active Issue and delivery boundary

- Issue [#33](https://github.com/TimeTreker/chromie/issues/33) owns bounded
  customer configuration of Chromie's Stable Mind.
- The project owner explicitly authorized this product feature and delivery as an
  exception to the current qualification-only line.
- The implementation reuses the existing `MindProfile`/Stable Mind authority. It adds
  no model call, semantic manager, environment variable, runtime switch, compatibility
  path, or parallel per-model personality.
- This patch does not close the pre-existing requirement to qualify an exact deployed
  provider/model and retain current-revision live and target evidence. After review of
  Issue #33, return to that qualification sequence unless the owner reprioritizes it.
- The continuing canonical focus remains the Goal-driven single-authority path documented
  in `docs/STATUS.md`; customer personalization supplies bounded Stable Mind context and
  does not move semantic authority out of GI, GA, Planner, or their existing owners.

## Implemented contract

```text
factory MindProfile
  + owner-confirmed bounded CustomerMindPersonalization
  -> one deterministically derived complete active MindProfile
  -> strict comparison with the current factory profile
  -> Host/Agent load the same profile
  -> one bounded projection for Fast Planner, Deep Planner, and Reflection
```

- `Worldview`, `HouseholdValues`, and `CustomerMindPersonalization` are independent
  typed sections inside the existing Stable Mind owner.
- Customer-editable fields are display name, pronouns, family role, one reviewed social
  style preset, up to eight worldview perspectives, and up to eight household values.
- Customer settings cannot edit or override core safety principles, privacy, consent,
  truthfulness, embodiment facts, evidence requirements, current user intent, or any
  other non-personalizable factory field.
- `apply_customer_mind_personalization()` derives a complete profile from the current
  factory profile. `validate_customer_mind_profile()` recomputes that result and rejects
  any difference, so editing the generated JSON cannot widen the authority surface.
- When `ORCH_MIND_PROFILE_PATH` is not explicit, Host and Agent use
  `.chromie/mind/active_profile.json` if it exists and passes customer-profile validation;
  otherwise they use the factory profile. Explicit profile-path behavior is preserved.
- Fast Planner, Deep Planner, and Selective Reflection receive the same bounded Stable
  Mind projection. The semantic contract establishes active configured name/role
  precedence while preserving the factory identity category and protected principles.
- `scripts/configure_chromie_mind.py` previews by default. `--apply` uses an atomic
  replacement, mode `0600`, monotonic customer versioning, and backup of an existing
  profile. `--reset` moves the active profile to a timestamped recoverable backup.
- Factory profile version is `0.7.0`. No active customer profile was written during this
  delivery; the preview path was exercised and remained absent.

## Repository surface delta

- New tracked files: two (`scripts/configure_chromie_mind.py` and its focused test).
- New current documents: zero. Existing configuration, mind, status, and user-manual
  owners were updated.
- New environment variables, runtime switches, architecture terms, compatibility paths,
  provider profiles, and model authorities: zero.
- The two-file growth is required for an executable customer/operator entry point and
  its independently owned regression coverage. No equivalent current script or test
  owner was available to consolidate.

## Evidence ledger

| Evidence | Result | Limit |
|---|---|---|
| Focused Mind/identity/configuration tests | 28 passed in 0.51s | Source/runtime contract only; no deployed model |
| Configuration preview | Produced `chromie_default_mind.customer` version `0.7.0+customer.1`; active path remained absent | Preview only; no persistent customer profile or restart |
| Repository policy gate | 15 rule families, 0 reviewed exceptions; passed | Static repository policy evidence |
| Canonical local gate | 2,051 main tests and 20 legacy Agent tests; passed | Automated source evidence on the pre-commit worktree |
| Documentation gate | 98 Markdown files; passed | Documentation structure/ownership only |
| Test ownership/static analysis | Passed through `./scripts/run_tests.sh` | Pinned local analysis only |
| `git diff --check` | Passed | Whitespace integrity only |

The first post-handoff `python scripts/check_docs.py` run failed because this checkpoint
did not explicitly retain the current Goal-driven single-authority focus. That ownership
wording and the exact focused-test count were corrected; the final documentation rerun
passed all 98 Markdown files.

No live Agent service, customer restart, deployed LLM, microphone, audible voice,
simulator, target hardware, or release evidence was produced for Issue #33.

## Exact resume point

1. Fetch and review the Issue #33 delivery revision:

   ```bash
   git fetch origin codex/customer-mind-personalization
   git switch codex/customer-mind-personalization
   git pull --ff-only origin codex/customer-mind-personalization
   git show --stat --oneline HEAD
   ```

2. Reproduce the local evidence:

   ```bash
   python scripts/check_repository_policies.py
   ./scripts/run_tests.sh
   python scripts/check_docs.py
   python scripts/configure_chromie_mind.py \
     --name Nova \
     --family-role "our household helper" \
     --social-style neutral \
     --worldview-perspective "Learning is something the household does together." \
     --household-value "Prefer calm explanations."
   ```

3. Review the Issue #33 contract before adding a GUI. A future customer-facing setup
   surface must authenticate the household owner, call the same bounded derivation and
   validation boundary, preserve preview/confirmation/recovery semantics, and must not
   expose raw profile JSON or protected factory fields.

4. Qualify the profile through an exact deployed model and a real service restart before
   claiming customer-visible behavior. Retain revision, factory-profile digest, generated
   customer-profile digest/version, model/runtime identity, prompts, outputs, and restart
   evidence. Then resume the pre-existing provider/live/target-evidence delivery line.

## Claim boundary

Issue #33 is source-complete and locally validated. It provides a real preview/apply/reset
CLI and shared runtime contract, but remains development-only. No graphical onboarding,
household authentication, deployed-model behavior, live voice, robot, or release claim is
made.
