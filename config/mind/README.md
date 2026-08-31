# Mind Profile Configuration

`chromie_default.json` is the maintained factory MindProfile. The normal runtime
uses it unless a validated customer profile exists at
`.chromie/mind/active_profile.json` or an operator explicitly selects another
profile through:

```bash
ORCH_MIND_PROFILE_PATH=config/mind/chromie_default.json
```

Concrete identity values belong here, not in Python defaults. An owner may edit
`identity.name`, `identity.age_description`, `identity.short_self_description`,
`identity.identity_answer_guidance`, pronouns, role wording, and the reviewed
mind policies without changing application code.

For normal customer setup, do not edit the factory file. Preview bounded settings:

```bash
python scripts/configure_chromie_mind.py \
  --name Nova \
  --family-role "our household helper" \
  --social-style neutral \
  --worldview-perspective "Learning is something we do together." \
  --household-value "Prefer calm explanations."
```

Review the JSON preview, then repeat with `--apply`. The command writes the active
profile atomically with owner-only file permissions. Restart Chromie to activate it.
It exposes only display name, pronouns, household role, one reviewed social-style
preset, bounded household worldview perspectives, and bounded household values.
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
