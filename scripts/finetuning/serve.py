"""Explicit isolated candidate launch using the existing SGLang Compose owner."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from .common import ROOT, Rejected, digest, file_digest, loads
from .model import LOCK_PATH


def command(*, merged: Path, image: str, port: int = 30001) -> list[str]:
    import yaml
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image) or not 1024 <= port <= 65535 or port == 30000:
        raise Rejected("pinned_local_image_and_separate_port_required")
    artifact = loads((merged / "chromie-adaptation.json").read_text())
    if artifact["base"]["lock_sha256"] != digest(loads(LOCK_PATH.read_text())):
        raise Rejected("merged_base_identity_mismatch")
    for name, sha in artifact["files"].items():
        if Path(name).name != name or file_digest(merged / name) != sha:
            raise Rejected("merged_file_identity_mismatch")
    class Loader(yaml.SafeLoader):
        pass
    def override(loader: Any, node: Any) -> Any:
        return loader.construct_sequence(node) if isinstance(node, yaml.SequenceNode) else loader.construct_mapping(node)
    Loader.add_constructor("!override", override)
    service = yaml.load((ROOT / "docker-compose.sglang.yml").read_text(), Loader=Loader)["services"]["chromie-llm"]
    original = service["command"]
    arguments = []
    changes = {"--model-path": "/model", "--served-model-name": "chromie-gemma4-12b-ft-candidate",
               "--host": "127.0.0.1", "--port": str(port)}
    index = 0
    while index < len(original):
        key = original[index]
        if key == "--revision":
            index += 2  # Local merged weights have their own manifest, not an HF revision.
        elif key in changes:
            arguments.extend([key, changes[key]])
            index += 2
        else:
            arguments.append(str(key))
            index += 1
    if any("${" in item for item in arguments):
        raise Rejected("unresolved_compose_command")
    return ["docker", "run", "--rm", "--name", "chromie-lora-candidate", "--gpus", "all", "--ipc", "host",
            "--network", "host", "-e", "HF_HUB_OFFLINE=1", "-e", "TRANSFORMERS_OFFLINE=1",
            "-e", "HF_HUB_DISABLE_TELEMETRY=1", "-v", str(merged.resolve()) + ":/model:ro",
            "--entrypoint", "python3", image, "-m", "sglang.launch_server", *arguments]


def launch(argv: list[str]) -> int:
    # Check a locally present image, never pull a mutable remote tag.
    image = argv[argv.index("python3") + 1]
    actual = subprocess.check_output(["docker", "image", "inspect", image, "--format", "{{.Id}}"], text=True).strip()
    if actual != image:
        raise Rejected("local_serving_image_identity_mismatch")
    return subprocess.call(argv)
