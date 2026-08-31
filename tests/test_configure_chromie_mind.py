from __future__ import annotations

import json
from pathlib import Path

from orchestrator.runtime.host_settings import HostSettingsSnapshot
from orchestrator.runtime.mind import MindManager
from scripts.configure_chromie_mind import main
from shared.chromie_contracts.mind import load_mind_profile


ROOT = Path(__file__).resolve().parents[1]
FACTORY = ROOT / "config" / "mind" / "chromie_default.json"


def test_customer_setup_previews_without_writing(tmp_path: Path, capsys: object) -> None:
    output = tmp_path / ".chromie" / "mind" / "active_profile.json"

    assert (
        main(
            [
                "--base-profile",
                str(FACTORY),
                "--output",
                str(output),
                "--name",
                "Nova",
                "--household-value",
                "Be patient while learning together.",
            ]
        )
        == 0
    )

    assert not output.exists()
    preview = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert preview["status"] == "preview"
    assert preview["identity"]["name"] == "Nova"
    assert "core_principles" in preview["locked_foundation"]


def test_customer_setup_applies_and_runtime_selects_active_profile(
    tmp_path: Path,
    capsys: object,
) -> None:
    output = tmp_path / ".chromie" / "mind" / "active_profile.json"

    assert (
        main(
            [
                "--base-profile",
                str(FACTORY),
                "--output",
                str(output),
                "--name",
                "Nova",
                "--pronoun",
                "she",
                "--pronoun",
                "her",
                "--family-role",
                "our household helper",
                "--social-style",
                "reserved",
                "--worldview-perspective",
                "Treat learning as something the household does together.",
                "--household-value",
                "Prefer calm explanations.",
                "--apply",
            ]
        )
        == 0
    )
    capsys.readouterr()  # type: ignore[attr-defined]

    active = load_mind_profile(output)
    assert active.identity.name == "Nova"
    assert active.customer_personalization is not None
    assert output.stat().st_mode & 0o777 == 0o600

    settings = HostSettingsSnapshot.from_env(project_root=tmp_path, environ={})
    assert settings.mind.profile_path == output.resolve()
    manager = MindManager.from_settings(settings.mind)
    assert manager.profile.identity.name == "Nova"
    assert manager.profile.social_interaction_style.preset == "reserved"


def test_customer_reset_is_recoverable(tmp_path: Path, capsys: object) -> None:
    output = tmp_path / ".chromie" / "mind" / "active_profile.json"
    main(
        [
            "--base-profile",
            str(FACTORY),
            "--output",
            str(output),
            "--name",
            "Nova",
            "--apply",
        ]
    )
    capsys.readouterr()  # type: ignore[attr-defined]

    assert main(["--output", str(output), "--reset"]) == 0
    result = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]

    assert result["status"] == "reset_to_factory_default"
    assert not output.exists()
    assert Path(result["recoverable_archive"]).is_file()
