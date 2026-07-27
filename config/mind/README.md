# Mind Profile Configuration

`chromie_default.json` is the maintained owner-editable MindProfile used by the
normal runtime through:

```bash
ORCH_MIND_PROFILE_PATH=config/mind/chromie_default.json
```

Concrete identity values belong here, not in Python defaults. An owner may edit
`identity.name`, `identity.age_description`, `identity.short_self_description`,
`identity.identity_answer_guidance`, pronouns, role wording, and the reviewed
mind policies without changing application code.

After editing the file:

1. increment the profile `version`;
2. keep `owner_approved=true` only after reviewing the complete profile;
3. rebuild/restart Chromie so the Orchestrator creates a new immutable mind
   context for subsequent turns;
4. run `PYTHONPATH=. python -m pytest -q tests/test_mind_profile.py
   tests/test_cognitive_identity_context.py`.

The LLM still decides whether a user is asking about identity and how to phrase
the answer. The Host does not implement name- or age-question phrase rules.
