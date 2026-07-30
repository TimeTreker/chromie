#!/usr/bin/env python3
"""Dependency-light executable repository engineering policy gate.

The checker validates stable structural and deployment rules. It intentionally
never evaluates prompt meaning, expected model choices, benchmark answers, or
user-facing language.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_local_runtime_exposure import audit_compose_sources  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXCEPTIONS = Path("config/repository_policy_exceptions.json")

RULE_PRODUCTION_ASSERT = "python.production_assert"
RULE_SILENT_BROAD_EXCEPTION = "python.silent_broad_exception"
RULE_DYNAMIC_EXECUTION = "python.dynamic_execution"
RULE_UNSAFE_SHELL = "python.unsafe_shell"
RULE_LOW_LEVEL_CONTRACT = "contracts.low_level_actuation_field"
RULE_LOCAL_EXPOSURE = "compose.local_loopback"
RULE_REMOVED_AUTHORITY = "architecture.removed_authority"
RULE_AGENT_SKILL_AUTHORITY = "agent_skills.execution_authority"
RULE_AGENT_SKILL_SELECTION = "agent_skills.model_authored_selection"
RULE_EXCEPTION_CONFIG = "policy.exception_config"
RULE_STALE_EXCEPTION = "policy.exception_stale"

EXCEPTION_TARGET_RULES = frozenset(
    {
        RULE_PRODUCTION_ASSERT,
        RULE_SILENT_BROAD_EXCEPTION,
        RULE_DYNAMIC_EXECUTION,
        RULE_UNSAFE_SHELL,
        RULE_LOW_LEVEL_CONTRACT,
        RULE_LOCAL_EXPOSURE,
        RULE_REMOVED_AUTHORITY,
        RULE_AGENT_SKILL_AUTHORITY,
        RULE_AGENT_SKILL_SELECTION,
    }
)

RUNTIME_PYTHON_ROOTS = (
    "agent/app",
    "orchestrator",
    "shared/chromie_runtime",
    "shared/chromie_contracts",
    "asr",
    "tts",
    "tts_candidates",
)
RUNTIME_PYTHON_FILES = ("scripts/generate_runtime_env.py",)
DYNAMIC_EXECUTION_ROOTS = (
    "agent/app",
    "orchestrator",
    "shared",
    "asr",
    "tts",
    "tts_candidates",
    "tools",
    "scripts",
)
MODEL_CONTRACT_ROOTS = ("agent/app", "shared/chromie_contracts")
AGENT_SKILL_ROOT = "agent/app/agent_skills"

_LOW_LEVEL_FIELD = re.compile(
    r"(?:^|_)(?:motor|joint|torque|actuator)(?:_|$)|"
    r"controller_?array|motor_targets?|joint_(?:positions?|angles?|velocities?|torques?)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, order=True)
class PolicyFinding:
    rule_id: str
    path: str
    line: int
    symbol: str
    message: str

    @property
    def exception_key(self) -> tuple[str, str, str]:
        return (self.rule_id, self.path, self.symbol)

    def render(self) -> str:
        location = self.path
        if self.line > 0:
            location = f"{location}:{self.line}"
        return f"{self.rule_id} {location} [{self.symbol}] {self.message}"


@dataclass(frozen=True)
class PolicyException:
    rule_id: str
    path: str
    symbol: str
    reason: str
    remove_when: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.rule_id, self.path, self.symbol)


class PolicyConfigurationError(ValueError):
    pass


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_python_files(root: Path, relative_roots: Sequence[str]) -> Iterator[Path]:
    seen: set[Path] = set()
    for relative in relative_roots:
        base = root / relative
        if base.is_file() and base.suffix == ".py":
            candidates = (base,)
        elif base.is_dir():
            candidates = base.rglob("*.py")
        else:
            continue
        for path in candidates:
            if any(
                part in {"__pycache__", ".venv", "venv", ".git"}
                for part in path.parts
            ):
                continue
            if path in seen:
                continue
            seen.add(path)
            yield path


def _parse_python(path: Path, root: Path) -> tuple[ast.AST | None, list[PolicyFinding]]:
    try:
        source = path.read_text(encoding="utf-8")
        return ast.parse(source, filename=str(path)), []
    except (OSError, UnicodeError, SyntaxError) as exc:
        return None, [
            PolicyFinding(
                rule_id=RULE_DYNAMIC_EXECUTION,
                path=_relative(path, root),
                line=getattr(exc, "lineno", 0) or 0,
                symbol="<module>",
                message=f"cannot inspect maintained Python source: {type(exc).__name__}: {exc}",
            )
        ]


def _call_qualname(node: ast.Call) -> str:
    def render(value: ast.AST) -> str:
        if isinstance(value, ast.Name):
            return value.id
        if isinstance(value, ast.Attribute):
            prefix = render(value.value)
            return f"{prefix}.{value.attr}" if prefix else value.attr
        return ""

    return render(node.func)


def _is_true_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _is_broad_exception_type(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Name):
        return node.id in {"Exception", "BaseException"}
    if isinstance(node, ast.Tuple):
        return any(_is_broad_exception_type(item) for item in node.elts)
    return False


def _is_trivially_silent_statement(node: ast.stmt) -> bool:
    if isinstance(node, (ast.Pass, ast.Continue, ast.Break)):
        return True
    if isinstance(node, ast.Return):
        return node.value is None or (
            isinstance(node.value, ast.Constant) and node.value.value is None
        )
    return False


class _PythonPolicyVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        path: Path,
        root: Path,
        inspect_runtime_failures: bool,
        inspect_dynamic_execution: bool,
    ) -> None:
        self.path = path
        self.root = root
        self.inspect_runtime_failures = inspect_runtime_failures
        self.inspect_dynamic_execution = inspect_dynamic_execution
        self.findings: list[PolicyFinding] = []
        self._symbols: list[str] = []

    @property
    def symbol(self) -> str:
        return ".".join(self._symbols) if self._symbols else "<module>"

    def _add(self, rule_id: str, node: ast.AST, message: str) -> None:
        self.findings.append(
            PolicyFinding(
                rule_id=rule_id,
                path=_relative(self.path, self.root),
                line=getattr(node, "lineno", 0) or 0,
                symbol=self.symbol,
                message=message,
            )
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._symbols.append(node.name)
        self.generic_visit(node)
        self._symbols.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._symbols.append(node.name)
        self.generic_visit(node)
        self._symbols.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._symbols.append(node.name)
        self.generic_visit(node)
        self._symbols.pop()

    def visit_Assert(self, node: ast.Assert) -> None:
        if self.inspect_runtime_failures:
            self._add(
                RULE_PRODUCTION_ASSERT,
                node,
                "production invariants must use explicit exceptions because assert is removed under python -O",
            )
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if (
            self.inspect_runtime_failures
            and _is_broad_exception_type(node.type)
            and node.body
            and all(_is_trivially_silent_statement(item) for item in node.body)
        ):
            self._add(
                RULE_SILENT_BROAD_EXCEPTION,
                node,
                "broad exception handler silently discards failure; narrow it or emit explicit degradation/evidence",
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self.inspect_dynamic_execution:
            qualname = _call_qualname(node)
            if qualname in {"eval", "exec", "builtins.eval", "builtins.exec"}:
                self._add(
                    RULE_DYNAMIC_EXECUTION,
                    node,
                    f"dynamic code execution through {qualname} is forbidden",
                )
            if qualname in {"os.system", "os.popen"}:
                self._add(
                    RULE_UNSAFE_SHELL,
                    node,
                    f"shell command execution through {qualname} is forbidden",
                )
            if qualname in {
                "asyncio.create_subprocess_shell",
                "subprocess.getoutput",
                "subprocess.getstatusoutput",
            }:
                self._add(
                    RULE_UNSAFE_SHELL,
                    node,
                    f"shell command execution through {qualname} is forbidden",
                )
            if qualname in {
                "subprocess.run",
                "subprocess.Popen",
                "subprocess.call",
                "subprocess.check_call",
                "subprocess.check_output",
            }:
                for keyword in node.keywords:
                    if keyword.arg == "shell" and _is_true_constant(keyword.value):
                        self._add(
                            RULE_UNSAFE_SHELL,
                            node,
                            f"{qualname}(..., shell=True) is forbidden",
                        )
        self.generic_visit(node)


def audit_python_policies(root: Path) -> list[PolicyFinding]:
    runtime_paths = set(
        _iter_python_files(root, (*RUNTIME_PYTHON_ROOTS, *RUNTIME_PYTHON_FILES))
    )
    dynamic_paths = set(_iter_python_files(root, DYNAMIC_EXECUTION_ROOTS))
    findings: list[PolicyFinding] = []
    for path in sorted(runtime_paths | dynamic_paths):
        tree, parse_findings = _parse_python(path, root)
        findings.extend(parse_findings)
        if tree is None:
            continue
        visitor = _PythonPolicyVisitor(
            path=path,
            root=root,
            inspect_runtime_failures=path in runtime_paths,
            inspect_dynamic_execution=path in dynamic_paths,
        )
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings


def _class_field_names(node: ast.ClassDef) -> Iterator[tuple[str, ast.AST]]:
    for statement in node.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            yield statement.target.id, statement
        elif isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    yield target.id, statement


def audit_model_contract_fields(root: Path) -> list[PolicyFinding]:
    findings: list[PolicyFinding] = []
    for path in sorted(_iter_python_files(root, MODEL_CONTRACT_ROOTS)):
        tree, parse_findings = _parse_python(path, root)
        findings.extend(parse_findings)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for field_name, field_node in _class_field_names(node):
                if _LOW_LEVEL_FIELD.search(field_name):
                    findings.append(
                        PolicyFinding(
                            rule_id=RULE_LOW_LEVEL_CONTRACT,
                            path=_relative(path, root),
                            line=getattr(field_node, "lineno", 0) or 0,
                            symbol=f"{node.name}.{field_name}",
                            message=(
                                "model-facing Chromie contracts may not expose raw motor, joint, torque, "
                                "actuator, or controller-array fields"
                            ),
                        )
                    )
    return findings


def _imported_module_names(tree: ast.AST) -> Iterator[tuple[str, ast.AST]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node
        elif isinstance(node, ast.ImportFrom):
            yield node.module or "", node


def audit_agent_skill_authority(root: Path) -> list[PolicyFinding]:
    findings: list[PolicyFinding] = []
    skill_root = root / AGENT_SKILL_ROOT
    if not skill_root.is_dir():
        return [
            PolicyFinding(
                rule_id=RULE_AGENT_SKILL_AUTHORITY,
                path=AGENT_SKILL_ROOT,
                line=0,
                symbol="<directory>",
                message="Agent Skill implementation root is missing",
            )
        ]

    forbidden_modules = {"subprocess", "runpy", "importlib", "ctypes"}
    forbidden_names = {
        "CapabilityRegistry",
        "CapabilityProvider",
        "CapabilityDefinition",
        "TrustedCapabilityRuntime",
        "TrustedSkillRuntime",
        "SkillRuntime",
    }
    forbidden_calls = {
        "register",
        "register_provider",
        "register_capability",
        "execute",
        "dispatch",
        "authorize",
        "grant_permission",
        "grant_confirmation",
    }
    forbidden_registry_methods = forbidden_calls | {"install", "load_plugin"}

    for path in sorted(skill_root.rglob("*.py")):
        tree, parse_findings = _parse_python(path, root)
        findings.extend(parse_findings)
        if tree is None:
            continue
        for module_name, node in _imported_module_names(tree):
            if module_name.split(".", 1)[0] in forbidden_modules:
                findings.append(
                    PolicyFinding(
                        rule_id=RULE_AGENT_SKILL_AUTHORITY,
                        path=_relative(path, root),
                        line=getattr(node, "lineno", 0) or 0,
                        symbol="<module>",
                        message=f"Agent Skill code may not import executable/plugin module {module_name!r}",
                    )
                )
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                findings.append(
                    PolicyFinding(
                        rule_id=RULE_AGENT_SKILL_AUTHORITY,
                        path=_relative(path, root),
                        line=getattr(node, "lineno", 0) or 0,
                        symbol="<module>",
                        message=f"Agent Skill code may not depend on execution authority {node.id}",
                    )
                )
            elif isinstance(node, ast.Call):
                qualname = _call_qualname(node)
                method = qualname.rsplit(".", 1)[-1]
                if method in forbidden_calls:
                    findings.append(
                        PolicyFinding(
                            rule_id=RULE_AGENT_SKILL_AUTHORITY,
                            path=_relative(path, root),
                            line=getattr(node, "lineno", 0) or 0,
                            symbol="<module>",
                            message=f"Agent Skill code may not invoke execution-authoritative method {method!r}",
                        )
                    )
            elif isinstance(node, ast.ClassDef) and node.name == "AgentSkillRegistry":
                for statement in node.body:
                    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)) and statement.name in forbidden_registry_methods:
                        findings.append(
                            PolicyFinding(
                                rule_id=RULE_AGENT_SKILL_AUTHORITY,
                                path=_relative(path, root),
                                line=statement.lineno,
                                symbol=f"AgentSkillRegistry.{statement.name}",
                                message="Agent Skill Registry must remain a passive read-only content index",
                            )
                        )
    return findings


def _attribute_chain(node: ast.Attribute) -> str:
    parts = [node.attr]
    value: ast.AST = node.value
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return ".".join(reversed(parts))


def _find_class(tree: ast.AST, name: str) -> ast.ClassDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _find_method(node: ast.ClassDef, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for statement in node.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)) and statement.name == name:
            return statement
    return None


def audit_agent_skill_selection(root: Path) -> list[PolicyFinding]:
    path = root / AGENT_SKILL_ROOT / "selection.py"
    tree, findings = _parse_python(path, root)
    if tree is None:
        return findings

    for module_name, node in _imported_module_names(tree):
        if module_name.split(".", 1)[0] in {"re", "regex"}:
            findings.append(
                PolicyFinding(
                    rule_id=RULE_AGENT_SKILL_SELECTION,
                    path=_relative(path, root),
                    line=getattr(node, "lineno", 0) or 0,
                    symbol="<module>",
                    message="Agent Skill selection may not use regex or phrase matching",
                )
            )

    service = _find_class(tree, "AgentSkillSelectionService")
    if service is None:
        findings.append(
            PolicyFinding(
                rule_id=RULE_AGENT_SKILL_SELECTION,
                path=_relative(path, root),
                line=0,
                symbol="AgentSkillSelectionService",
                message="model-authored Agent Skill selection service is missing",
            )
        )
        return findings

    select_method = _find_method(service, "select")
    if select_method is None or not any(
        isinstance(node, ast.Call) and _call_qualname(node).endswith("client.generate")
        for node in ast.walk(select_method or service)
    ):
        findings.append(
            PolicyFinding(
                rule_id=RULE_AGENT_SKILL_SELECTION,
                path=_relative(path, root),
                line=getattr(select_method or service, "lineno", 0) or 0,
                symbol="AgentSkillSelectionService.select",
                message="non-empty Agent Skill selection must remain model-authored through the configured client",
            )
        )

    discover = _find_method(service, "_discover_candidates")
    if discover is None:
        findings.append(
            PolicyFinding(
                rule_id=RULE_AGENT_SKILL_SELECTION,
                path=_relative(path, root),
                line=service.lineno,
                symbol="AgentSkillSelectionService._discover_candidates",
                message="bounded candidate discovery method is missing",
            )
        )
    else:
        semantic_attributes = {"text", "language", "goals", "context_summary"}
        for node in ast.walk(discover):
            if isinstance(node, ast.Attribute):
                chain = _attribute_chain(node)
                if chain.startswith("request.") and node.attr in semantic_attributes:
                    findings.append(
                        PolicyFinding(
                            rule_id=RULE_AGENT_SKILL_SELECTION,
                            path=_relative(path, root),
                            line=node.lineno,
                            symbol="AgentSkillSelectionService._discover_candidates",
                            message=(
                                f"Host candidate discovery may not inspect semantic input {chain!r}; "
                                "only the model may make the final Skill choice"
                            ),
                        )
                    )

    for candidate in ast.walk(tree):
        if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            token in candidate.name.lower() for token in ("keyword", "phrase_rule", "route_skill")
        ):
            findings.append(
                PolicyFinding(
                    rule_id=RULE_AGENT_SKILL_SELECTION,
                    path=_relative(path, root),
                    line=candidate.lineno,
                    symbol=candidate.name,
                    message="Host keyword/phrase/route Skill selectors are forbidden",
                )
            )
        if isinstance(candidate, (ast.If, ast.IfExp)):
            test = candidate.test
            has_text = any(
                isinstance(item, ast.Attribute) and item.attr == "text"
                for item in ast.walk(test)
            )
            has_literal = any(
                isinstance(item, ast.Constant) and isinstance(item.value, str)
                for item in ast.walk(test)
            )
            if has_text and has_literal:
                findings.append(
                    PolicyFinding(
                        rule_id=RULE_AGENT_SKILL_SELECTION,
                        path=_relative(path, root),
                        line=candidate.lineno,
                        symbol="AgentSkillSelectionService",
                        message="Host conditional selection may not compare user text with literal phrases",
                    )
                )
    return findings


def audit_compose_policy(root: Path) -> list[PolicyFinding]:
    compose = root / "docker-compose.yml"
    if not compose.is_file():
        return [
            PolicyFinding(
                rule_id=RULE_LOCAL_EXPOSURE,
                path="docker-compose.yml",
                line=0,
                symbol="services",
                message="maintained local Compose profile is missing",
            )
        ]
    return [
        PolicyFinding(
            rule_id=RULE_LOCAL_EXPOSURE,
            path="docker-compose.yml",
            line=0,
            symbol="services",
            message=message,
        )
        for message in audit_compose_sources((compose,))
    ]


def audit_removed_authority(root: Path) -> list[PolicyFinding]:
    checker_name = "check_" + "router" + "_removed.py"
    checker_label = "scripts/" + checker_name
    checker = root / "scripts" / checker_name
    if not checker.is_file():
        return [
            PolicyFinding(
                rule_id=RULE_REMOVED_AUTHORITY,
                path=checker_label,
                line=0,
                symbol="main",
                message="removed-authority guard is missing",
            )
        ]
    completed = subprocess.run(
        [sys.executable, str(checker)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return []
    detail = (completed.stderr or completed.stdout or "Router guard failed").strip()
    return [
        PolicyFinding(
            rule_id=RULE_REMOVED_AUTHORITY,
            path=checker_label,
            line=0,
            symbol="main",
            message=detail[:4000],
        )
    ]


def load_policy_exceptions(path: Path, root: Path) -> tuple[list[PolicyException], list[PolicyFinding]]:
    relative = _relative(path, root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [], [
            PolicyFinding(
                rule_id=RULE_EXCEPTION_CONFIG,
                path=relative,
                line=0,
                symbol="exceptions",
                message=f"cannot load policy exception registry: {type(exc).__name__}: {exc}",
            )
        ]
    try:
        if not isinstance(raw, dict) or set(raw) != {"schema_version", "exceptions"}:
            raise PolicyConfigurationError(
                "registry must contain exactly schema_version and exceptions"
            )
        if raw["schema_version"] != "1.0":
            raise PolicyConfigurationError("schema_version must be '1.0'")
        entries = raw["exceptions"]
        if not isinstance(entries, list):
            raise PolicyConfigurationError("exceptions must be a list")
        exceptions: list[PolicyException] = []
        seen: set[tuple[str, str, str]] = set()
        expected_fields = {"rule_id", "path", "symbol", "reason", "remove_when"}
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or set(entry) != expected_fields:
                raise PolicyConfigurationError(
                    f"exceptions[{index}] must contain exactly {sorted(expected_fields)}"
                )
            values = {key: str(value).strip() for key, value in entry.items()}
            if values["rule_id"] not in EXCEPTION_TARGET_RULES:
                raise PolicyConfigurationError(
                    f"exceptions[{index}].rule_id is not exception-eligible"
                )
            exception_path = Path(values["path"])
            if (
                not values["path"]
                or exception_path.is_absolute()
                or ".." in exception_path.parts
            ):
                raise PolicyConfigurationError(
                    f"exceptions[{index}].path must be a safe repository-relative path"
                )
            if not values["symbol"]:
                raise PolicyConfigurationError(
                    f"exceptions[{index}].symbol must be non-empty"
                )
            if len(values["reason"]) < 20:
                raise PolicyConfigurationError(
                    f"exceptions[{index}].reason must explain the reviewed exception"
                )
            if len(values["remove_when"]) < 20:
                raise PolicyConfigurationError(
                    f"exceptions[{index}].remove_when must define a concrete removal condition"
                )
            exception = PolicyException(**values)
            if exception.key in seen:
                raise PolicyConfigurationError(
                    f"duplicate exception key {exception.key!r}"
                )
            seen.add(exception.key)
            exceptions.append(exception)
        return exceptions, []
    except PolicyConfigurationError as exc:
        return [], [
            PolicyFinding(
                rule_id=RULE_EXCEPTION_CONFIG,
                path=relative,
                line=0,
                symbol="exceptions",
                message=str(exc),
            )
        ]


def apply_policy_exceptions(
    findings: Iterable[PolicyFinding],
    exceptions: Sequence[PolicyException],
    *,
    exception_path: str,
) -> tuple[list[PolicyFinding], int]:
    raw = sorted(set(findings))
    exception_by_key = {item.key: item for item in exceptions}
    matched: set[tuple[str, str, str]] = set()
    remaining: list[PolicyFinding] = []
    for finding in raw:
        if finding.exception_key in exception_by_key:
            matched.add(finding.exception_key)
        else:
            remaining.append(finding)
    for exception in exceptions:
        if exception.key not in matched:
            remaining.append(
                PolicyFinding(
                    rule_id=RULE_STALE_EXCEPTION,
                    path=exception_path,
                    line=0,
                    symbol="/".join(exception.key),
                    message=(
                        "exception no longer matches a live finding; remove it instead of retaining a permanent baseline"
                    ),
                )
            )
    return sorted(set(remaining)), len(matched)


def audit_repository(
    root: Path = ROOT,
    *,
    exception_path: Path | None = None,
) -> tuple[list[PolicyFinding], int]:
    root = root.resolve()
    configured_exception_path = exception_path or (root / DEFAULT_EXCEPTIONS)
    findings: list[PolicyFinding] = []
    findings.extend(audit_python_policies(root))
    findings.extend(audit_model_contract_fields(root))
    findings.extend(audit_compose_policy(root))
    findings.extend(audit_removed_authority(root))
    findings.extend(audit_agent_skill_authority(root))
    findings.extend(audit_agent_skill_selection(root))
    exceptions, config_findings = load_policy_exceptions(
        configured_exception_path, root
    )
    findings.extend(config_findings)
    if config_findings:
        return sorted(set(findings)), 0
    return apply_policy_exceptions(
        findings,
        exceptions,
        exception_path=_relative(configured_exception_path, root),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="repository root to inspect",
    )
    parser.add_argument(
        "--exceptions",
        type=Path,
        help="exception registry path; relative paths are resolved from --root",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    exception_path = args.exceptions
    if exception_path is not None and not exception_path.is_absolute():
        exception_path = root / exception_path
    findings, suppressed = audit_repository(root, exception_path=exception_path)
    if args.json:
        print(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "failed" if findings else "passed",
                    "suppressed_findings": suppressed,
                    "findings": [
                        {
                            "rule_id": item.rule_id,
                            "path": item.path,
                            "line": item.line,
                            "symbol": item.symbol,
                            "message": item.message,
                        }
                        for item in findings
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
    elif findings:
        print("Repository engineering policy check failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding.render()}", file=sys.stderr)
    else:
        print(
            "Repository engineering policies passed "
            f"({len(EXCEPTION_TARGET_RULES)} rule families, {suppressed} reviewed exceptions)"
        )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
