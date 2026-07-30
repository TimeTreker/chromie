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
