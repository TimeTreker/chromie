# Test Suite Maintenance

Chromie's automated suite is organized by behavioral ownership rather than by
historical date or milestone wrapper. A large test count is not itself a quality
claim.

## Rules

- Keep one canonical owner for each scenario execution.
- Move unique assertions out of dated regression wrappers before deleting them.
- Use table-driven cases when setup and boundary are identical, but retain
  separate tests when different architectural or safety authorities are being
  exercised.
- Preserve real model failure outputs as replay fixtures.
- Do not count mocked unit tests as live model qualification.
- Report exact current counts from command output rather than hardcoding them in
  status documents.
- Prefer user-outcome acceptance for release behavior and use internal-path
  assertions only for component qualification.
- Keep deterministic module/unit truth in fixtures and executable assertions;
  do not route objective tests through an LLM reviewer.
- Use semantic review only for declared qualitative dimensions, and retain the
  deterministic and semantic verdicts separately in hybrid reports.
- Keep comprehensive orchestration thin: it may invoke maintained test owners,
  collect correlated evidence, and package artifacts, but scenario definitions
  and pass/fail truth remain in the benchmark contracts, fixtures, and review
  schema they already own.
- Keep `scripts/qualification/run_comprehensive_test.sh --dry-run` side-effect
  free and update its command contract whenever a maintained entrypoint changes.

## Audit commands

```bash
./scripts/run_tests.sh
python scripts/test_matrix.py --list
python scripts/general_ability_acceptance.py --mode check
./scripts/qualification/run_comprehensive_test.sh --dry-run
```

When removing tests, record the original and resulting file/method counts,
runtime, migrated assertions, and full-suite result. Do not remove a test solely
to reduce the count.
