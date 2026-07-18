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

## Audit commands

```bash
./scripts/run_tests.sh
python scripts/test_matrix.py --list
python scripts/general_ability_acceptance.py --mode check
```

When removing tests, record the original and resulting file/method counts,
runtime, migrated assertions, and full-suite result. Do not remove a test solely
to reduce the count.
