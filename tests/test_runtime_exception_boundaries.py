from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_runtime_exception_boundaries import (
    audit_runtime_exception_boundaries,
    scan_broad_handlers,
)


class RuntimeExceptionBoundaryInventoryTests(unittest.TestCase):
    def _root(self, source: str) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        path = root / "orchestrator" / "sample.py"
        path.parent.mkdir(parents=True)
        path.write_text(source, encoding="utf-8")
        (root / "config").mkdir()
        return root

    @staticmethod
    def _write_inventory(root: Path, handlers: list[dict]) -> Path:
        path = root / "config" / "runtime_exception_boundaries.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "1.2",
                    "body_hash_algorithm": "normalized_source_v1",
                    "handlers": handlers,
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_missing_broad_handler_classification_fails(self) -> None:
        root = self._root(
            "def run():\n    try:\n        work()\n    except Exception:\n        return None\n"
        )
        inventory = self._write_inventory(root, [])
        findings = audit_runtime_exception_boundaries(
            root,
            inventory_path=inventory,
        )
        self.assertTrue(any("not classified" in item.message for item in findings))

    def test_exact_symbol_level_inventory_passes(self) -> None:
        root = self._root(
            "class Runner:\n    def run(self):\n        try:\n            work()\n        except Exception:\n            return None\n"
        )
        handler = scan_broad_handlers(root)[0]
        inventory = self._write_inventory(
            root,
            [
                {
                    "path": handler.path,
                    "symbol": handler.symbol,
                    "ordinal": handler.ordinal,
                    "classification": "fail_closed_boundary",
                    "owner": "runtime",
                    "contract": "Returns a typed failure without claiming completion.",
                    "review_status": "reviewed",
                    "body_sha256": handler.body_sha256,
                    "failure_signals": list(handler.failure_signals),
                }
            ],
        )
        self.assertEqual(
            audit_runtime_exception_boundaries(root, inventory_path=inventory),
            [],
        )

    def test_stale_inventory_entry_fails(self) -> None:
        root = self._root("def run():\n    return 1\n")
        inventory = self._write_inventory(
            root,
            [
                {
                    "path": "orchestrator/sample.py",
                    "symbol": "run",
                    "ordinal": 1,
                    "classification": "fail_closed_boundary",
                    "owner": "runtime",
                    "contract": "No completion claim.",
                    "review_status": "reviewed",
                    "body_sha256": "0" * 64,
                    "failure_signals": ["return"],
                }
            ],
        )
        findings = audit_runtime_exception_boundaries(root, inventory_path=inventory)
        self.assertTrue(any("stale" in item.message for item in findings))
    def test_wrong_hash_algorithm_fails(self) -> None:
        root = self._root(
            "def run():\n    try:\n        work()\n    except Exception:\n        return None\n"
        )
        handler = scan_broad_handlers(root)[0]
        inventory = root / "config" / "runtime_exception_boundaries.json"
        inventory.write_text(
            json.dumps(
                {
                    "schema_version": "1.2",
                    "body_hash_algorithm": "ast_dump_v1",
                    "handlers": [
                        {
                            "path": handler.path,
                            "symbol": handler.symbol,
                            "ordinal": handler.ordinal,
                            "classification": "fail_closed_boundary",
                            "owner": "runtime",
                            "contract": "Returns a typed failure.",
                            "review_status": "reviewed",
                            "body_sha256": handler.body_sha256,
                            "failure_signals": list(handler.failure_signals),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        findings = audit_runtime_exception_boundaries(
            root, inventory_path=inventory
        )
        self.assertTrue(
            any("body_hash_algorithm" in item.message for item in findings)
        )

    def test_changed_handler_body_requires_re_review(self) -> None:
        root = self._root(
            "def run():\n    try:\n        work()\n    except Exception:\n        return None\n"
        )
        handler = scan_broad_handlers(root)[0]
        inventory = self._write_inventory(
            root,
            [
                {
                    "path": handler.path,
                    "symbol": handler.symbol,
                    "ordinal": handler.ordinal,
                    "classification": "fail_closed_boundary",
                    "owner": "runtime",
                    "contract": "Returns a typed failure without claiming completion.",
                    "review_status": "reviewed",
                    "body_sha256": handler.body_sha256,
                    "failure_signals": list(handler.failure_signals),
                }
            ],
        )
        (root / "orchestrator" / "sample.py").write_text(
            "def run():\n    try:\n        work()\n    except Exception:\n        log_error()\n        return None\n",
            encoding="utf-8",
        )
        findings = audit_runtime_exception_boundaries(root, inventory_path=inventory)
        self.assertTrue(any("body changed" in item.message for item in findings))
