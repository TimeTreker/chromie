from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FAILURE_STATUSES = {"failed", "error", "timed_out", "cancelled", "refused"}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def _catalog_by_id(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = snapshot.get("capabilities")
    if not isinstance(raw, list):
        return {}
    catalog: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        capability_id = str(item.get("capability_id") or "").strip()
        if capability_id:
            catalog[capability_id] = item
    return catalog


def _skill_successes(record: dict[str, Any]) -> set[str]:
    results = record.get("skill_results")
    if not isinstance(results, list):
        status = str(record.get("execution_status") or "").lower()
        if status in FAILURE_STATUSES:
            return set()
        selected = record.get("selected_skills")
        return {str(skill) for skill in selected or [] if str(skill).strip()}
    successes: set[str] = set()
    for result in results:
        if not isinstance(result, dict):
            continue
        skill_id = str(result.get("skill_id") or "").strip()
        status = str(result.get("status") or "").lower()
        if skill_id and status not in FAILURE_STATUSES:
            successes.add(skill_id)
    return successes


def build_prompt_tier_overlay(
    *,
    experience_records: list[dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
    promote_count: int,
    demote_count: int,
    min_success_rate: float,
    minimum_demotion_records: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    selected_counts: Counter[str] = Counter()
    success_counts: Counter[str] = Counter()
    for record in experience_records:
        selected = {
            str(skill).strip()
            for skill in record.get("selected_skills") or []
            if str(skill).strip()
        }
        selected_counts.update(selected)
        success_counts.update(selected & _skill_successes(record))

    capability_ids = set(catalog) | set(selected_counts)
    prompt_tiers: dict[str, dict[str, Any]] = {}
    audit_entries: list[dict[str, Any]] = []
    total_records = len(experience_records)
    for capability_id in sorted(capability_ids):
        item = catalog.get(capability_id, {})
        old_tier = str(item.get("prompt_tier") or "rare").strip().lower()
        locked = item.get("prompt_tier_locked") is True
        selected_count = int(selected_counts.get(capability_id, 0))
        success_count = int(success_counts.get(capability_id, 0))
        success_rate = success_count / selected_count if selected_count else 0.0
        new_tier = ""
        if selected_count >= promote_count and success_rate >= min_success_rate:
            new_tier = "common"
        elif (
            total_records >= minimum_demotion_records
            and selected_count <= demote_count
            and old_tier == "common"
        ):
            new_tier = "rare"
        if not new_tier or new_tier == old_tier:
            continue
        audit = {
            "event": "capability_prompt_tier_candidate",
            "capability_id": capability_id,
            "old_prompt_tier": old_tier,
            "new_prompt_tier": new_tier,
            "selected_count": selected_count,
            "success_count": success_count,
            "success_rate": round(success_rate, 4),
            "experience_record_count": total_records,
            "source": "experience",
            "locked": locked,
        }
        if locked:
            audit["event"] = "capability_prompt_tier_locked_skip"
            audit["reason"] = "prompt_tier_locked prevented experience promotion/demotion"
            audit_entries.append(audit)
            continue
        reason = (
            f"experience selected {selected_count} time(s), "
            f"success_rate={success_rate:.2f}, records={total_records}"
        )
        prompt_tiers[capability_id] = {
            "prompt_tier": new_tier,
            "source": "experience",
            "reason": reason,
            "evidence": {
                "selected_count": selected_count,
                "success_count": success_count,
                "success_rate": round(success_rate, 4),
                "experience_record_count": total_records,
            },
        }
        audit["reason"] = reason
        audit_entries.append(audit)

    overlay = {
        "schema_version": "0.1",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "experience_tier_tuner",
        "prompt_tiers": prompt_tiers,
    }
    return overlay, audit_entries


def _append_audit(path: Path, entries: list[dict[str, Any]]) -> None:
    if not entries:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for item in entries:
            item = {**item, "logged_at": datetime.now(UTC).isoformat()}
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def _write_overlay(path: Path, overlay: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(overlay, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build an auditable capability prompt-tier overlay from Chromie experience logs."
    )
    parser.add_argument("--experience", type=Path, default=ROOT / ".chromie" / "experience" / "experience.jsonl")
    parser.add_argument("--catalog-snapshot", type=Path, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / ".chromie" / "experience" / "capability_prompt_tier_overrides.json",
    )
    parser.add_argument(
        "--audit-output",
        type=Path,
        default=ROOT / ".chromie" / "experience" / "capability_prompt_tier_audit.jsonl",
    )
    parser.add_argument("--promote-count", type=int, default=3)
    parser.add_argument("--demote-count", type=int, default=0)
    parser.add_argument("--min-success-rate", type=float, default=0.5)
    parser.add_argument("--minimum-demotion-records", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    records = _read_jsonl(args.experience)
    catalog = _catalog_by_id(_read_json(args.catalog_snapshot)) if args.catalog_snapshot else {}
    overlay, audit_entries = build_prompt_tier_overlay(
        experience_records=records,
        catalog=catalog,
        promote_count=max(1, args.promote_count),
        demote_count=max(0, args.demote_count),
        min_success_rate=max(0.0, min(1.0, args.min_success_rate)),
        minimum_demotion_records=max(0, args.minimum_demotion_records),
    )
    if args.dry_run:
        print(json.dumps(overlay, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    _write_overlay(args.output, overlay)
    _append_audit(args.audit_output, audit_entries)
    print(
        f"wrote {len(overlay['prompt_tiers'])} prompt tier override(s) "
        f"and {len(audit_entries)} audit event(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
