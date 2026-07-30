#!/usr/bin/env python3
"""Reject host-wide publications in Chromie's local Docker Compose profile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "[::1]"}


def _normalize_host(value: object) -> str:
    return str(value or "").strip()


def _host_from_port_string(spec: str) -> str:
    value = spec.strip().strip('"').strip("'")
    value = value.split("/", 1)[0]
    if value.startswith("["):
        closing = value.find("]")
        if closing > 0 and value[closing + 1 :].startswith(":"):
            return value[1:closing]
        return ""
    parts = value.rsplit(":", 2)
    if len(parts) == 3:
        return parts[0]
    return ""


def _port_description(port: object) -> str:
    if isinstance(port, dict):
        published = port.get("published", "?")
        target = port.get("target", "?")
        protocol = port.get("protocol", "tcp")
        return f"{published}->{target}/{protocol}"
    return str(port)


def audit_resolved_compose(config: object) -> list[str]:
    """Audit a ``docker compose config --format json`` result."""

    if not isinstance(config, dict):
        return ["resolved Compose configuration must be a JSON object"]
    services = config.get("services")
    if not isinstance(services, dict):
        return ["resolved Compose configuration must contain a services object"]

    findings: list[str] = []
    for service_name, service in sorted(services.items()):
        if not isinstance(service, dict):
            findings.append(f"service {service_name!r} must resolve to an object")
            continue
        if service.get("network_mode") == "host":
            findings.append(
                f"service {service_name!r} uses host networking, which bypasses "
                "the local-only publication boundary"
            )
        ports = service.get("ports", [])
        if ports is None:
            continue
        if not isinstance(ports, list):
            findings.append(f"service {service_name!r} ports must resolve to a list")
            continue
        for port in ports:
            if isinstance(port, dict):
                host = _normalize_host(port.get("host_ip"))
            elif isinstance(port, str):
                host = _host_from_port_string(port)
            else:
                host = ""
            if host not in _LOOPBACK_HOSTS:
                findings.append(
                    f"service {service_name!r} publishes {_port_description(port)} on "
                    f"{host or 'an unspecified/wildcard host interface'}; use 127.0.0.1"
                )
    return findings


def _strip_inline_comment(value: str) -> str:
    in_single = False
    in_double = False
    for index, character in enumerate(value):
        if character == "'" and not in_double:
            in_single = not in_single
        elif character == '"' and not in_single:
            in_double = not in_double
        elif character == "#" and not in_single and not in_double:
            return value[:index].rstrip()
    return value.rstrip()


def audit_compose_source(path: Path) -> list[str]:
    """Dependency-light source guard for maintained Compose YAML files.

    The maintained files use short string port syntax. Mapping-form publications
    fail closed so a future syntax change must extend this checker deliberately.
    Runtime startup also audits Docker Compose's resolved JSON representation.
    """

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [f"cannot read {path}: {exc}"]

    findings: list[str] = []
    in_services = False
    current_service = ""
    ports_indent: int | None = None

    for line_number, raw_line in enumerate(lines, start=1):
        content = _strip_inline_comment(raw_line)
        stripped = content.strip()
        if not stripped:
            continue
        indent = len(content) - len(content.lstrip(" "))

        if indent == 0:
            in_services = stripped == "services:"
            current_service = ""
            ports_indent = None
            continue
        if not in_services:
            continue

        if indent == 2 and stripped.endswith(":") and not stripped.startswith("-"):
            current_service = stripped[:-1].strip()
            ports_indent = None
            continue
        if not current_service:
            continue

        if indent == 4 and stripped.startswith("network_mode:"):
            mode = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            if mode == "host":
                findings.append(
                    f"{path}:{line_number}: service {current_service!r} uses host networking"
                )

        if indent == 4 and stripped == "ports:":
            ports_indent = indent
            continue
        if ports_indent is not None and indent <= ports_indent:
            ports_indent = None
        if ports_indent is None or indent <= ports_indent:
            continue
        if not stripped.startswith("-"):
            continue

        spec = stripped[1:].strip()
        if not spec or ":" not in spec:
            findings.append(
                f"{path}:{line_number}: service {current_service!r} uses unsupported "
                "port syntax; declare an explicit 127.0.0.1 host publication"
            )
            continue
        host = _host_from_port_string(spec)
        if host not in _LOOPBACK_HOSTS:
            findings.append(
                f"{path}:{line_number}: service {current_service!r} publishes {spec} on "
                f"{host or 'an unspecified/wildcard host interface'}; use 127.0.0.1"
            )

    return findings


def audit_compose_sources(paths: Iterable[Path]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        findings.extend(audit_compose_source(path))
    return findings


def _load_resolved_json(path: str) -> Any:
    if path == "-":
        return json.load(sys.stdin)
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "compose_files",
        nargs="*",
        type=Path,
        help="maintained Compose YAML files to audit directly",
    )
    parser.add_argument(
        "--resolved-json",
        metavar="PATH",
        help="audit Docker Compose's resolved JSON; use '-' for stdin",
    )
    args = parser.parse_args(argv)

    findings = audit_compose_sources(args.compose_files)
    if args.resolved_json:
        try:
            resolved = _load_resolved_json(args.resolved_json)
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(f"cannot read resolved Compose JSON: {exc}")
        else:
            findings.extend(audit_resolved_compose(resolved))

    if not args.compose_files and not args.resolved_json:
        parser.error("provide at least one Compose source file or --resolved-json")

    if findings:
        for finding in findings:
            print(f"[exposure][error] {finding}", file=sys.stderr)
        return 1

    print("[exposure] local runtime host publications are loopback-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
