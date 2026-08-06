# Static Analysis Ratchets

Chromie adopts static analysis incrementally. The gates protect reviewed defect
classes without authorizing a repository-wide formatting rewrite or changing
semantic ownership.

## Ruff

The maintained Ruff version is pinned in `requirements-test.txt`. The gate runs:

```bash
python scripts/run_ruff.py
```

The configuration in `ruff.toml` explicitly enables only the reviewed
high-signal families:

- `F` for undefined names, unused imports, and related Pyflakes defects;
- `E4`, `E7`, and `E9` for import, statement, and syntax-class errors;
- `B` for flake8-bugbear correctness findings;
- `ASYNC` for unsafe asynchronous patterns.

`config/ruff_scope.txt` is the monotonic initial ratchet. Entries must be sorted,
unique, repository-relative, and present. Expanding the ratchet requires the new
scope to pass before it is committed. Removing a checked path requires a separate
reviewed architecture decision.

Ruff formatting is not part of this gate. Suppressions must be narrow and local;
a blanket ignore list or `noqa` baseline is not an accepted migration strategy.

Install the pinned test dependencies before running the complete gate in a clean
environment:

```bash
python -m pip install -r requirements-test.txt
./scripts/run_tests.sh
```

Passing this gate is implementation evidence only. It does not establish live,
hardware, or release qualification.

## Mypy

The maintained Mypy version is pinned in `requirements-test.txt`. The gate runs:

```bash
python scripts/run_mypy.py
```

`config/mypy_scope.txt` currently contains four files and is a monotonic
ratchet over selected clean contracts and tooling boundaries. `mypy.ini` requires complete function
annotations, checks untyped bodies, forbids implicit optional values, and reports
unsafe `Any` returns and stale ignores. It does not skip imports or enable a
whole-tree error suppression.

The current baseline contains four files. The mechanism is implemented and the
pinned Mypy 2.3.0 command passes that scope on the 2026-07-31 maintained tree
without ignores, but four files are not meaningful package coverage. An August
2 package/file expansion was committed from an environment that did not contain
the pinned Mypy executable. The first dependency-complete Python 3.11/3.12 CI
run proved that expanded scope had 169 pre-existing errors, so it was not a
valid ratchet expansion. The scope is therefore restored to the last verified
contract rather than suppressing those errors or falsely treating them as new
vocal-Issue regressions.

After the existing gate is clean, the queued expansion replaces file-by-file
contract entries with all 23 current Python files under
`shared/chromie_contracts/`, then adds independently owned Orchestrator runtime
packages after their decomposition boundaries stabilize. A directory/package
entry must include future files automatically.

A checked path may leave the ratchet only through a separate reviewed
architecture change. New modules should enter once their real optionality,
containers, callables, and async return types are clean; broad `Any` conversion
is not an accepted migration strategy.

## Accepted expansion order

After current-revision target evidence closes and the relevant boundaries are
stable, expand Mypy through complete ownership scopes: first
`shared/chromie_contracts/`, then coherent slices of `orchestrator/runtime/`. Do
not add isolated showcase files merely to increase a count, and do not use broad
`Any`, import skipping, global ignores, or scope removal to manufacture a pass.

## Source qualification reporting

`python scripts/run_source_qualification.py` executes the checked source gate
contract in `config/source_qualification.json` and writes a revision-bound JSON
report. Missing pinned Ruff or Mypy executables are reported as `unavailable`
and block qualification; they are never silently skipped. The report is source
evidence only and always excludes target, audio, simulator, robot, LAN, and
release claims. Use `--skip-full-suite` only for a diagnostic partial report.
