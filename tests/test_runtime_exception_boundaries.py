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
            json.dumps({"schema_version": "1.0", "handlers": handlers}),
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
                }
            ],
        )
        findings = audit_runtime_exception_boundaries(root, inventory_path=inventory)
        self.assertTrue(any("stale" in item.message for item in findings))
