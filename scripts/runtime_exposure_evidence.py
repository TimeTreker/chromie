#!/usr/bin/env python3
"""Collect and verify deployed loopback/LAN exposure evidence.

Local collection proves that maintained services are published only on loopback
and remain reachable from the Chromie host. Remote collection must run from a
second LAN machine: it first proves network reachability through an explicit
control port, then proves that Chromie's internal service ports are unreachable.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORTS = (5000, 8092, 9001, 11434)
LOOPBACK_HOSTS = {"127.0.0.1", "::1"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path | None, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path is not None:
        resolved = path.expanduser().resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _git_state(root: Path = ROOT) -> dict[str, Any]:
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True
        ).strip()
    )
    return {"revision": revision, "dirty": dirty}


def _tcp_probe(host: str, port: int, timeout_s: float) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return {"host": host, "port": port, "reachable": True, "error": None}
    except OSError as exc:
        return {
            "host": host,
            "port": port,
            "reachable": False,
            "error": f"{exc.__class__.__name__}: {exc}",
        }


def _compose_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.compose_json:
        return _read(args.compose_json.expanduser().resolve())
    if not args.skip_env_build:
        subprocess.run(["./scripts/build_runtime_env.sh"], cwd=ROOT, check=True)
    command = [
        "docker",
        "compose",
        "--env-file",
        str(args.env_file),
        "-f",
        str(args.compose_file),
        "config",
        "--format",
        "json",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "cannot resolve Docker Compose configuration: "
            + (completed.stderr or completed.stdout).strip()
        )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise ValueError("resolved Compose configuration must be an object")
    return payload


def _published_ports(compose: dict[str, Any]) -> list[dict[str, Any]]:
    published: list[dict[str, Any]] = []
    services = compose.get("services")
    if not isinstance(services, dict):
        raise ValueError("resolved Compose configuration has no services object")
    for service_name, service in services.items():
        if not isinstance(service, dict):
            continue
        ports = service.get("ports")
        if not isinstance(ports, list):
            continue
        for item in ports:
            if isinstance(item, dict):
                host_ip = str(item.get("host_ip") or "")
                published_port = item.get("published")
                target = item.get("target")
                protocol = str(item.get("protocol") or "tcp")
            elif isinstance(item, str):
                parts = item.rsplit(":", 2)
                if len(parts) == 3:
                    host_ip, published_port, target = parts
                elif len(parts) == 2:
                    host_ip, (published_port, target) = "", parts
                else:
                    continue
                protocol = "tcp"
            else:
                continue
            try:
                published_int = int(published_port)
                target_int = int(target)
            except (TypeError, ValueError):
                continue
            published.append(
                {
                    "service": str(service_name),
                    "host_ip": host_ip,
                    "published": published_int,
                    "target": target_int,
                    "protocol": protocol,
                }
            )
    return sorted(published, key=lambda item: (item["published"], item["service"]))


def _expected_ports(args: argparse.Namespace) -> list[int]:
    return sorted(set(args.port or DEFAULT_PORTS))


def collect_local(args: argparse.Namespace) -> dict[str, Any]:
    compose = _compose_payload(args)
    published = _published_ports(compose)
    expected = _expected_ports(args)
    errors: list[str] = []
    by_port = {item["published"]: item for item in published}
    for port in expected:
        item = by_port.get(port)
        if item is None:
            errors.append(f"expected host publication {port} is missing")
        elif item["host_ip"] not in LOOPBACK_HOSTS:
            errors.append(
                f"port {port} is published on {item['host_ip']!r}, not loopback"
            )
    unexpected = [
        item for item in published if item["host_ip"] not in LOOPBACK_HOSTS
    ]
    if unexpected:
        errors.append("one or more maintained services are broadly published")
    probes = [_tcp_probe(args.local_host, port, args.timeout_s) for port in expected]
    for probe in probes:
        if probe["reachable"] is not True:
            errors.append(f"local port {probe['port']} is not reachable")
    source = _git_state()
    if source["dirty"]:
        errors.append("local exposure evidence requires a clean Chromie checkout")
    return {
        "schema_version": 1,
        "evidence_type": "local_runtime_exposure",
        "captured_at": _utc_now(),
        "observer": socket.gethostname(),
        "target_host": args.target_host,
        "source": source,
        "expected_ports": expected,
        "published_ports": published,
        "local_probes": probes,
        "passed": not errors,
        "errors": errors,
    }


def collect_remote(args: argparse.Namespace) -> dict[str, Any]:
    expected = _expected_ports(args)
    control = _tcp_probe(args.control_host, args.control_port, args.timeout_s)
    probes = [_tcp_probe(args.target_host, port, args.timeout_s) for port in expected]
    errors: list[str] = []
    if control["reachable"] is not True:
        errors.append(
            "control port is unreachable; the remote probe does not prove LAN path connectivity"
        )
    exposed = [probe["port"] for probe in probes if probe["reachable"] is True]
    if exposed:
        errors.append(
            "Chromie internal service ports are reachable from the LAN observer: "
            + ", ".join(str(port) for port in exposed)
        )
    return {
        "schema_version": 1,
        "evidence_type": "remote_runtime_exposure_probe",
        "captured_at": _utc_now(),
        "observer": socket.gethostname(),
        "target_host": args.target_host,
        "expected_ports": expected,
        "control_probe": control,
        "service_probes": probes,
        "passed": not errors,
        "errors": errors,
    }


def verify_reports(
    local: dict[str, Any],
    remote: dict[str, Any],
    *,
    expected_revision: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    if local.get("evidence_type") != "local_runtime_exposure":
        errors.append("local report has the wrong evidence_type")
    if remote.get("evidence_type") != "remote_runtime_exposure_probe":
        errors.append("remote report has the wrong evidence_type")
    if local.get("passed") is not True:
        errors.append("local exposure report did not pass")
    if remote.get("passed") is not True:
        errors.append("remote exposure report did not pass")
    if local.get("target_host") != remote.get("target_host"):
        errors.append("local and remote reports target different hosts")
    local_ports = local.get("expected_ports")
    remote_ports = remote.get("expected_ports")
    if local_ports != remote_ports or not isinstance(local_ports, list) or not local_ports:
        errors.append("local and remote reports do not cover the same non-empty port set")
    source = local.get("source")
    if not isinstance(source, dict):
        errors.append("local report has no source identity")
    else:
        if source.get("dirty") is not False:
            errors.append("local report is not bound to a clean checkout")
        if expected_revision and source.get("revision") != expected_revision:
            errors.append(
                f"local report revision {source.get('revision')!r} does not match {expected_revision!r}"
            )
    control = remote.get("control_probe")
    if not isinstance(control, dict) or control.get("reachable") is not True:
        errors.append("remote report has no reachable control probe")
    service_probes = remote.get("service_probes")
    if not isinstance(service_probes, list) or any(
        not isinstance(item, dict) or item.get("reachable") is not False
        for item in service_probes
    ):
        errors.append("remote report does not prove every internal port is unreachable")
    return {
        "schema_version": 1,
        "evidence_type": "runtime_exposure_qualification",
        "passed": not errors,
        "errors": errors,
        "target_host": local.get("target_host"),
        "ports": local_ports if isinstance(local_ports, list) else [],
        "source_revision": source.get("revision") if isinstance(source, dict) else None,
        "release_qualified": False,
    }


def verify(args: argparse.Namespace) -> dict[str, Any]:
    local = _read(args.local_report.expanduser().resolve())
    remote = _read(args.remote_report.expanduser().resolve())
    expected = args.expected_revision
    if expected is None:
        try:
            expected = _git_state()["revision"]
        except Exception:
            expected = None
    return verify_reports(local, remote, expected_revision=expected)


def _add_ports(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--port",
        type=int,
        action="append",
        help="Internal service port to probe. Repeat to replace the maintained default set.",
    )
    parser.add_argument("--timeout-s", type=float, default=2.0)
    parser.add_argument("--output", type=Path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    local = sub.add_parser("local", help="Collect loopback publication and local reachability evidence.")
    _add_ports(local)
    local.add_argument("--target-host", required=True, help="LAN address used by the second-machine probe.")
    local.add_argument("--local-host", default="127.0.0.1")
    local.add_argument("--compose-file", type=Path, default=Path("docker-compose.yml"))
    local.add_argument("--env-file", type=Path, default=Path(".env.runtime"))
    local.add_argument("--compose-json", type=Path)
    local.add_argument("--skip-env-build", action="store_true")

    remote = sub.add_parser("remote", help="Run from a second LAN machine.")
    _add_ports(remote)
    remote.add_argument("--target-host", required=True)
    remote.add_argument("--control-host", required=True)
    remote.add_argument("--control-port", type=int, required=True)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--local-report", type=Path, required=True)
    verify_parser.add_argument("--remote-report", type=Path, required=True)
    verify_parser.add_argument("--expected-revision")
    verify_parser.add_argument("--output", type=Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "local":
            report = collect_local(args)
        elif args.command == "remote":
            report = collect_remote(args)
        elif args.command == "verify":
            report = verify(args)
        else:
            raise ValueError(f"unsupported command: {args.command}")
    except Exception as exc:
        print(f"[runtime-exposure-evidence][error] {exc}", file=sys.stderr)
        return 2
    _write(args.output, report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
