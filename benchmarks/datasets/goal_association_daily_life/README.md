# Goal Association Daily-Life Corpus

Audience: GA prompt/contract reviewers and qualification operators. Each JSON file
below `scenarios/<split>/<category>/` is an independently reviewable authoritative
scenario, while `dataset.json` owns aggregate coverage. This document is operational
guidance only. An existing product document cannot own the corpus because benchmark
coverage, split isolation, asset identity, and review provenance are executable
qualification facts rather than runtime behavior policy.

Issue [#34](https://github.com/TimeTreker/chromie/issues/34) owns this work. The
corpus contains exactly 1,500 cases: 100 bilingual daily-life semantic seeds, each
expanded into the same 15-member Goal-continuity contrast set. Unlike the GI corpus,
every case supplies a production-shaped `CognitiveWorkRequest` containing accepted GI
Responsibilities and bounded existing/recent Goal state.

The corpus covers new creation, continue, modify, clarification answers, confirm,
reject, cancel, pause, resume, terminal reference, replacement, unrelated new work,
merge, split, and a deliberately retained mixed association-plus-creation contract
probe. The final probe currently cannot pass the exclusive GA decision discriminant;
it is labeled `known_contract_gap` rather than being hidden with a prompt workaround.

Validate the complete directory-discovered corpus with:

```bash
python benchmarks/datasets/goal_association_daily_life/validate.py
```

The validator discovers all 1,500 separate scenario files, reconstructs each production
decoder Schema, checks the accepted reference DTO through the real
`GoalAssociationResolver`, verifies Responsibility conservation and contrast membership,
and binds the complete sorted scenario tree to the manifest digest. The 100 known
contract-gap cases must remain rejected for the documented mixed-continuity reason until
the project owner authorizes a global DTO/Schema amendment.

All scenarios remain `training_eligible=false` and lack independent semantic review.
Mechanical validity does not qualify the prompt, a deployed model, service behavior,
voice, simulator, target robot, or release.
