from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOTS = (
    ROOT / "agent" / "app",
    ROOT / "orchestrator",
    ROOT / "shared" / "chromie_contracts",
)
DEFERRED_RUNTIME_IDENTIFIERS = (
    "affect_simulation",
    "ambient_autonomy",
    "broader_autonomy",
    "competence_calibration",
    "multi_user_identity",
)


def test_deferred_cognition_extensions_have_no_production_runtime_switch() -> None:
    hits: list[str] = []
    for root in PRODUCTION_ROOTS:
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for identifier in DEFERRED_RUNTIME_IDENTIFIERS:
                if identifier in text:
                    hits.append(f"{path.relative_to(ROOT)}:{identifier}")

    assert hits == [], (
        "deferred cognition extensions require an originating episode, an explicit "
        "authority/irreducibility review, and a qualification plan before a production "
        "runtime switch is introduced: " + ", ".join(hits)
    )


def test_charter_requires_admission_before_deferred_cognition_implementation() -> None:
    charter = (ROOT / "docs" / "PROJECT_CHARTER.md").read_text(encoding="utf-8")
    required = (
        "Deferred cognition admission",
        "originating episode",
        "authority/irreducibility review",
        "qualification plan",
    )
    for phrase in required:
        assert phrase in charter
