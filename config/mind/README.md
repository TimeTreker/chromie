# Mind Profile Configuration

`chromie_default.json` is the maintained factory MindProfile: Chromie, a
twelve-year-old girl. The normal runtime uses it unless a validated customer
profile exists at `.chromie/mind/active_profile.json`, and uses the selected
profile's own social style. The shipped `.env.common` sets neither override; an
operator may explicitly select another profile or force a social-style preset in
`.env.local`:

```bash
ORCH_MIND_PROFILE_PATH=config/mind/chromie_default.json   # optional override
ORCH_SOCIAL_INTERACTION_STYLE_PRESET=lively              # optional override
```

The customer may configure name, pronouns, family role, and character style: one
reviewed choice from `character_styles.json` that sets personality traits, self-concept
and spoken style together with the matching social-expression preset (`lively_cute` is
the factory character; also `gentle_warm`, `calm_steady`, `cool_independent`). The
family role is household relationship wording, never a service or assistant role. The
Charter rule `IDENTITY-TRUTH-001` applies to whatever identity is configured: she
speaks only as herself, never as a robot, AI, model, assistant, or service, and
never asserts a falsehood about her nature.

Concrete identity values belong here, not in Python defaults. A deployment owner
(operator, not the project owner who approves the Charter) may edit the customer
fields above (`identity.name`, pronouns, `identity.family_role`, character style) and
also `identity.age_description`, `identity.short_self_description`,
`identity.identity_answer_guidance`, and personality expression, without changing
application code. No other identity field is deployment-configurable.
`IDENTITY-TRUTH-001` lives in Social Cognition's fixed instructions, not in this
file, so `identity_answer_guidance` may shape how she answers but cannot remove or
override it.

For normal customer setup, do not edit the factory file. Preview bounded settings:

```bash
python scripts/configure_chromie_mind.py \
  --name Nova \
  --family-role "the youngest in our family" \
  --character-style calm_steady \
  --worldview-perspective "Learning is something we do together." \
  --household-value "Prefer calm explanations."
```

Review the JSON preview, then repeat with `--apply`. The command writes the active
profile atomically with owner-only file permissions. Restart Chromie to activate it.
It exposes only display name, pronouns, household role, one reviewed character style
(`--list-character-styles`), bounded household worldview perspectives, and bounded
household values.
Core principles, safety/reflex policy, privacy, consent, authorization, embodiment
truth, capabilities, providers, prompts, models, and permissions are not customer
settings. An existing profile is backed up before replacement.

Reset is recoverable:

```bash
python scripts/configure_chromie_mind.py --reset
```

Reset moves the active customer profile to a timestamped `.bak` archive and restores
the factory profile on the next restart.

After editing the file:

1. increment the profile `version`;
2. keep `owner_approved=true` only after reviewing the complete profile;
3. rebuild/restart Chromie so the Orchestrator creates a new immutable mind
   context for subsequent turns;
4. run `PYTHONPATH=. python -m pytest -q tests/test_mind_profile.py
   tests/test_cognitive_identity_context.py`.

The LLM still decides whether a user is asking about identity and how to phrase
the answer. The Host does not implement name- or age-question phrase rules.
