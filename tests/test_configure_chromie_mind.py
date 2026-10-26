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
                "--character-style",
                "calm_steady",
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


def test_shipped_env_layers_keep_customer_profile_and_its_social_style(
    tmp_path: Path,
    capsys: object,
) -> None:
    from scripts.generate_runtime_env import parse_env_file

    output = tmp_path / ".chromie" / "mind" / "active_profile.json"
    main(
        [
            "--base-profile",
            str(FACTORY),
            "--output",
            str(output),
            "--name",
            "Nova",
            "--character-style",
            "calm_steady",
            "--apply",
        ]
    )
    capsys.readouterr()  # type: ignore[attr-defined]

    shipped_layers = [
        ROOT / ".env.common",
        *sorted((ROOT / "env" / "profiles").glob("*.env")),
        *sorted((ROOT / "env" / "modes").glob("*.env")),
    ]
    for layer in shipped_layers:
        values = parse_env_file(layer)
        assert "ORCH_MIND_PROFILE_PATH" not in values, layer
        assert "ORCH_SOCIAL_INTERACTION_STYLE_PRESET" not in values, layer

    common = dict(parse_env_file(ROOT / ".env.common"))
    settings = HostSettingsSnapshot.from_env(project_root=tmp_path, environ=common)
    assert settings.mind.profile_path == output.resolve()
    manager = MindManager.from_settings(settings.mind)
    assert manager.profile.identity.name == "Nova"
    assert manager.profile.social_interaction_style.preset == "reserved"

    output.unlink()
    factory_copy = tmp_path / "config" / "mind" / "chromie_default.json"
    factory_copy.parent.mkdir(parents=True)
    factory_copy.write_text(FACTORY.read_text(encoding="utf-8"), encoding="utf-8")
    factory_settings = HostSettingsSnapshot.from_env(project_root=tmp_path, environ=common)
    assert factory_settings.mind.profile_path == factory_copy.resolve()
    assert MindManager.from_settings(factory_settings.mind).profile.identity.name == "Chromie"


def test_operator_social_style_override_applies_only_when_set(tmp_path: Path) -> None:
    settings = HostSettingsSnapshot.from_env(
        project_root=ROOT,
        environ={
            "ORCH_MIND_PROFILE_PATH": str(FACTORY),
            "ORCH_SOCIAL_INTERACTION_STYLE_PRESET": "neutral",
        },
    )
    assert settings.mind.profile_path == FACTORY.resolve()
    assert MindManager.from_settings(settings.mind).profile.social_interaction_style.preset == "neutral"
