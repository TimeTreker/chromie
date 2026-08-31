#!/usr/bin/env python3
"""Create, preview, or reset Chromie's bounded customer MindProfile."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.chromie_contracts.mind import (
    CustomerMindPersonalization,
    MindProfile,
    active_customer_mind_profile_path,
    apply_customer_mind_personalization,
    default_mind_profile_path,
    load_mind_profile,
    validate_customer_mind_profile,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Configure customer-owned identity presentation, social style, "
            "worldview perspectives, and household values without exposing "
            "Chromie's locked safety/authority foundation."
        )
    )
    parser.add_argument(
        "--base-profile",
        type=Path,
        default=default_mind_profile_path(ROOT),
        help="Factory MindProfile used as the locked foundation.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=active_customer_mind_profile_path(ROOT),
        help="Active customer profile path used automatically at next startup.",
    )
    parser.add_argument("--name", help="Customer-selected display/self-reference name.")
    parser.add_argument(
        "--pronoun",
        action="append",
        dest="pronouns",
        help="Pronoun to use; repeat for multiple forms.",
    )
    parser.add_argument("--family-role", help="Customer-selected household role wording.")
    parser.add_argument(
        "--social-style",
        choices=("courteous", "neutral", "reserved"),
        help="Reviewed social interaction style preset.",
    )
    parser.add_argument(
        "--worldview-perspective",
        action="append",
        dest="worldview_perspectives",
        help="Household perspective; repeat up to eight times.",
    )
    parser.add_argument(
        "--household-value",
        action="append",
        dest="household_values",
        help="Household preference/value; repeat up to eight times.",
    )
    parser.add_argument(
        "--clear-worldview-perspectives",
        action="store_true",
        help="Clear existing customer worldview perspectives.",
    )
    parser.add_argument(
        "--clear-household-values",
        action="store_true",
        help="Clear existing customer household values.",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--apply",
        action="store_true",
        help="Confirm and atomically save this preview for the next startup.",
    )
    action.add_argument(
        "--reset",
        action="store_true",
        help="Archive the active customer profile and return to factory defaults.",
    )
    return parser


def _existing_personalization(
    output: Path,
    *,
    factory_profile: MindProfile,
) -> CustomerMindPersonalization | None:
    if not output.is_file():
        return None
    existing = load_mind_profile(output)
    validate_customer_mind_profile(existing, factory_profile)
    return existing.customer_personalization


def _personalization_from_args(
    args: argparse.Namespace,
    previous: CustomerMindPersonalization | None,
) -> CustomerMindPersonalization:
    prior = previous or CustomerMindPersonalization()
    worldview_perspectives = (
        []
        if args.clear_worldview_perspectives
        else (
            args.worldview_perspectives
            if args.worldview_perspectives is not None
            else prior.worldview_perspectives
        )
    )
    household_values = (
        []
        if args.clear_household_values
        else (
            args.household_values
            if args.household_values is not None
            else prior.household_values
        )
    )
    return CustomerMindPersonalization(
        personalization_version=(
            prior.personalization_version + 1 if previous is not None else 1
        ),
        display_name=args.name if args.name is not None else prior.display_name,
        pronouns=args.pronouns if args.pronouns is not None else prior.pronouns,
        family_role=(
            args.family_role if args.family_role is not None else prior.family_role
        ),
        social_style_preset=(
            args.social_style
            if args.social_style is not None
            else prior.social_style_preset
        ),
        worldview_perspectives=worldview_perspectives,
        household_values=household_values,
    )


def _preview(profile: MindProfile, *, output: Path) -> dict[str, object]:
    identity = profile.identity
    personalization = profile.customer_personalization
    if personalization is None:
        raise ValueError("customer preview requires customer personalization")
    return {
        "status": "preview",
        "active_profile_path": str(output.resolve()),
        "profile_id": profile.profile_id,
        "profile_version": profile.version,
        "customer_personalization": personalization.model_dump(mode="json"),
        "identity": {
            "name": identity.name,
            "pronouns": list(identity.pronouns),
            "age_description": identity.age_description,
            "kind": identity.kind,
            "family_role": identity.family_role,
            "embodiment_boundary": "robotic body; no biological-human claim",
        },
        "social_style": profile.social_interaction_style.preset,
        "worldview_perspectives": list(profile.worldview.household_perspectives),
        "household_values": list(profile.household_values.statements),
        "locked_foundation": [
            "core_principles",
            "safety_and_reflex_policy",
            "privacy_consent_and_authorization",
            "truthful_embodiment_and_capability_evidence",
            "providers_models_prompts_and_permissions",
        ],
        "activation": "restart Chromie after --apply",
    }


def _atomic_write(path: Path, payload: dict[str, object]) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if path.is_file():
        existing = load_mind_profile(path)
        version = (
            existing.customer_personalization.personalization_version
            if existing.customer_personalization is not None
            else "unknown"
        )
        backup = path.with_name(f"{path.name}.v{version}.bak")
        shutil.copy2(path, backup)
        backup.chmod(0o600)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(0o600)
    os.replace(temporary, path)
    return backup


def _reset(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {
            "status": "already_factory_default",
            "active_profile_path": str(path.resolve()),
        }
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = path.with_name(f"{path.name}.reset-{timestamp}.bak")
    path.replace(archive)
    archive.chmod(0o600)
    return {
        "status": "reset_to_factory_default",
        "active_profile_path": str(path.resolve()),
        "recoverable_archive": str(archive.resolve()),
        "activation": "restart Chromie",
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = args.output.expanduser()
    if not output.is_absolute():
        output = ROOT / output
    if args.reset:
        print(json.dumps(_reset(output), ensure_ascii=False, indent=2))
        return 0

    base_profile = load_mind_profile(args.base_profile.expanduser())
    if base_profile.customer_personalization is not None:
        raise ValueError("--base-profile must be a factory profile")
    previous = _existing_personalization(output, factory_profile=base_profile)
    personalization = _personalization_from_args(args, previous)
    active_profile = apply_customer_mind_personalization(
        base_profile,
        personalization,
    )
    preview = _preview(active_profile, output=output)
    if not args.apply:
        preview["next_step"] = "Review this preview, then repeat with --apply."
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return 0

    backup = _atomic_write(
        output,
        active_profile.model_dump(mode="json"),
    )
    validate_customer_mind_profile(load_mind_profile(output), base_profile)
    preview["status"] = "applied"
    preview["backup"] = str(backup.resolve()) if backup is not None else None
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
