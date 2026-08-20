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
from check_runtime_exception_boundaries import (  # noqa: E402
    audit_runtime_exception_boundaries,
)

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
RULE_HOST_SEMANTIC_AUTHORITY = "architecture.host_semantic_authority"
RULE_LEGACY_PHRASE_AGENTS = "architecture.legacy_phrase_agents"
RULE_MEMORY_MODEL_AUTHORED = "memory.model_authored_update"
RULE_CANONICAL_CAPABILITY_ID = "contracts.canonical_capability_identity"
RULE_EXCEPTION_CONFIG = "policy.exception_config"
RULE_STALE_EXCEPTION = "policy.exception_stale"
RULE_UNCLASSIFIED_BROAD_EXCEPTION = "python.unclassified_broad_exception"

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
        RULE_HOST_SEMANTIC_AUTHORITY,
        RULE_LEGACY_PHRASE_AGENTS,
        RULE_MEMORY_MODEL_AUTHORED,
        RULE_CANONICAL_CAPABILITY_ID,
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
        "CapabilityRuntime",
        "SkillRegistry",
        "SkillProvider",
        "SkillDefinition",
        "SkillRuntime",
        "TrustedCapabilityRuntime",
        "TrustedSkillRuntime",
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
        forbidden_request_attributes = {"text", "language", "context_summary"}
        forbidden_goal_attributes = {
            "goal_id",
            "description",
            "bindings",
            "success_criteria",
            "resource_kind",
        }
        for node in ast.walk(discover):
            if not isinstance(node, ast.Attribute):
                continue
            chain = _attribute_chain(node)
            if chain.startswith("request.") and node.attr in forbidden_request_attributes:
                findings.append(
                    PolicyFinding(
                        rule_id=RULE_AGENT_SKILL_SELECTION,
                        path=_relative(path, root),
                        line=node.lineno,
                        symbol="AgentSkillSelectionService._discover_candidates",
                        message=(
                            f"Host candidate discovery may not inspect semantic input {chain!r}; "
                            "only exact typed Goal applicability fields may narrow candidates "
                            "before the model makes the final Skill choice"
                        ),
                    )
                )
            if chain.startswith("goal.") and node.attr in forbidden_goal_attributes:
                findings.append(
                    PolicyFinding(
                        rule_id=RULE_AGENT_SKILL_SELECTION,
                        path=_relative(path, root),
                        line=node.lineno,
                        symbol="AgentSkillSelectionService._discover_candidates",
                        message=(
                            f"Host candidate discovery may not inspect Goal semantic field {chain!r}; "
                            "only output_mode and information_domain are allowed for mechanical "
                            "Agent Skill applicability filtering"
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



def _source_policy_finding(
    *,
    root: Path,
    path: str,
    rule_id: str,
    symbol: str,
    message: str,
    line: int = 0,
) -> PolicyFinding:
    return PolicyFinding(
        rule_id=rule_id,
        path=path,
        line=line,
        symbol=symbol,
        message=message,
    )


def audit_semantic_authority_boundaries(root: Path) -> list[PolicyFinding]:
    """Reject Host semantic delegation, phrase agents, and memory inference."""

    findings: list[PolicyFinding] = []
    forbidden_files = {
        "orchestrator/runtime/deepthinking_policy.py": RULE_HOST_SEMANTIC_AUTHORITY,
        "agent/app/agents/motion_planner.py": RULE_LEGACY_PHRASE_AGENTS,
        "agent/app/agents/robot_pose_controller.py": RULE_LEGACY_PHRASE_AGENTS,
    }
    for relative, rule_id in forbidden_files.items():
        if (root / relative).exists():
            findings.append(
                _source_policy_finding(
                    root=root,
                    path=relative,
                    rule_id=rule_id,
                    symbol="<module>",
                    message="removed Host semantic authority must not be reintroduced",
                )
            )

    source_checks = {
        "orchestrator/orchestrator.py": (
            RULE_HOST_SEMANTIC_AUTHORITY,
            (
                "DeepThinkingDelegationPolicy",
                "ORCH_CONDITIONAL_DEEPTHINK_ENABLED",
                "_apply_conditional_deepthinking_policy",
                "_ability_unavailable_response",
                "abilities.localized_speech",
                "_looks_like_embodied_request",
                "embodied_terms =",
            ),
            "ordinary deep-thinking and user-facing wording must remain model/Core-authored",
        ),
        "agent/app/runtime.py": (
            RULE_LEGACY_PHRASE_AGENTS,
            (
                "MotionPlannerAgent",
                "RobotPoseControllerAgent",
                "allow_legacy_rule_agents",
            ),
            "caller context must not reactivate phrase-based semantic agents",
        ),
        "agent/app/capabilities/catalog.py": (
            RULE_HOST_SEMANTIC_AUTHORITY,
            (
                "_semantic_action_score",
                "_is_forward_motion_query",
                "_STOP_WORDS",
                "def _tokens",
                "def _score",
                "def _route_for(",
                "def _agents_for",
                "searchable_text",
            ),
            "capability retrieval may expose declared contracts but may not score or route user language",
        ),
        "agent/app/capabilities/validator.py": (
            RULE_HOST_SEMANTIC_AUTHORITY,
            (
                "normalize_enum_string",
                "def enum_key",
                "def enum_joined_key",
                "aliases =",
            ),
            "Capability arguments require exact schema values; handwritten language aliases may not repair model output",
        ),
        "agent/app/cognitive_core/goal_interpreter/model_interpreter.py": (
            RULE_HOST_SEMANTIC_AUTHORITY,
            (
                "_decision_has_weather_semantics",
                "_decision_selects_weather_tool",
                "weather_semantics_require_tool_route",
                "Current or upcoming weather and forecast questions",
                "Use route=tool and intent=weather_query for weather lookup",
                "For weather/tool lookup",
                "Use tool for changing external facts, including current weather",
                "direct_question_form",
                "missing_aliases",
            ),
            "Goal Interpretation may not contain domain routing or punctuation/alias semantic fallbacks",
        ),
        "orchestrator/runtime/interaction_coordinator.py": (
            RULE_HOST_SEMANTIC_AUTHORITY,
            (
                "_truth_reconciliation_message",
                "_looks_like_warning_correction",
                "host_truth_reconciliation",
            ),
            "Host truth reconciliation must preserve safe model speech or fail closed without authoring semantic wording",
        ),
        "agent/app/agents/tool.py": (
            RULE_HOST_SEMANTIC_AUTHORITY,
            (
                "_is_weather_request",
                '"weather" in intent',
                '"forecast" in intent',
                "services.weather_client",
                "weather_client.lookup",
                "client.lookup(query)",
            ),
            "ToolAgent may dispatch only from an exact model-authored Capability identity",
        ),
        "orchestrator/runtime/conversation_state.py": (
            RULE_HOST_SEMANTIC_AUTHORITY,
            (
                "DEFAULT_FOLLOWUP_PHRASES",
                "DEFAULT_NEW_TOPIC_STARTERS",
                "ORCH_CONVERSATION_FOLLOWUP_PHRASES",
                "ORCH_CONVERSATION_NEW_TOPIC_STARTERS",
                "is_followup_reference",
                "is_new_topic_like",
                "soft_idle_new_topic",
                "DEFAULT_RESET_PHRASES",
                "ORCH_CONVERSATION_RESET_PHRASES",
                "is_explicit_reset",
                "_looks_like_meaningful_task_text",
            ),
            "conversation state may apply typed model decisions and hard idle expiry but may not classify discourse or reset semantics",
        ),
        "orchestrator/runtime/abilities.py": (
            RULE_HOST_SEMANTIC_AUTHORITY,
            (
                "speech_templates",
                'implementation="host_tts"',
                'implementation="host_speech"',
                "unavailable_en",
                "unavailable_zh",
            ),
            "the static ability ontology may describe responsibility but may not author user-facing speech",
        ),
        "agent/app/cognitive_core/goal_interpreter/engine.py": (
            RULE_HOST_SEMANTIC_AUTHORITY,
            (
                "_unique_capability_suffix_match",
                "action_claim_terms",
            ),
            "Goal Interpretation may validate exact model output but may not guess capabilities or speech meaning from words",
        ),
        "orchestrator/runtime/confirmation.py": (
            RULE_HOST_SEMANTIC_AUTHORITY,
            (
                "_AFFIRMATIVE_PHRASES",
                "_NEGATIVE_PHRASES",
                "_OPERATIONAL_INTERRUPT_PHRASES",
                "_normalize_reply",
            ),
            "confirmation language meaning must come from typed Goal Association output",
        ),
        "shared/chromie_contracts/semantic_task.py": (
            RULE_HOST_SEMANTIC_AUTHORITY,
            (
                "pending_action_stage_direction_claims",
                "_STAGE_DIRECTION_PATTERN",
                "_SKILL_TOKEN_STOPWORDS",
            ),
            "semantic contracts may carry typed claims but may not infer them from speech tokens",
        ),
        "shared/chromie_contracts/perception.py": (
            RULE_HOST_SEMANTIC_AUTHORITY,
            ("_DEPENDENCY_ALIASES",),
            "perception contracts must preserve exact typed dependencies instead of applying semantic aliases",
        ),
        "agent/app/schema.py": (
            RULE_HOST_SEMANTIC_AUTHORITY,
            (
                "_INTERNAL_PLAN_LABEL_RE",
                "_INTERNAL_EXECUTION_RE",
                "reject_contract_marker_as_spoken_text",
                "contract_markers =",
            ),
            "spoken-text sanitization may remove mechanical identifiers but may not classify natural-language meaning",
        ),
        "agent/app/cognitive_core/goal_interpreter/schema.py": (
            RULE_HOST_SEMANTIC_AUTHORITY,
            (
                'decision.speak_first = "你是指什么？"',
                'decision.speak_first = "What do you mean?"',
                "Core-authored process acknowledgement",
                'metadata.get("ability_proposals")',
                'normalized in {"missing_ability"',
                "reject_contract_marker_as_spoken_text",
                "contract_markers =",
            ),
            "Goal Interpretation contracts may preserve exact typed model output but may not synthesize wording or semantic aliases",
        ),
        "orchestrator/runtime/session.py": (
            RULE_HOST_SEMANTIC_AUTHORITY,
            ("_looks_like_failure_speech",),
            "observability severity must use structured events rather than user-facing phrase classification",
        ),
        "orchestrator/runtime/host_settings.py": (
            RULE_HOST_SEMANTIC_AUTHORITY,
            ("reset_phrases", "ORCH_CONVERSATION_RESET_PHRASES"),
            "runtime configuration may not expose semantic phrase tables",
        ),
        "agent/app/social_attention.py": (
            RULE_CANONICAL_CAPABILITY_ID,
            (
                "exact skill_id values",
                "Each behavior contains skill_id",
            ),
            "Social Attention model prompts must emit canonical capability_id",
        ),
    }
    for relative, (rule_id, tokens, message) in source_checks.items():
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if token in text:
                findings.append(
                    _source_policy_finding(
                        root=root,
                        path=relative,
                        rule_id=rule_id,
                        symbol=token,
                        message=message,
                    )
                )

    semantic_rule_paths = (
        "agent/app/agents/conversation.py",
        "agent/app/agents/capability.py",
        "agent/app/capabilities/catalog.py",
        "agent/app/capabilities/validator.py",
        "agent/app/cognitive_core/goal_interpreter/engine.py",
        "agent/app/cognitive_core/goal_interpreter/model_interpreter.py",
        "agent/app/cognitive_core/goal_interpreter/schema.py",
        "agent/app/schema.py",
        "orchestrator/orchestrator.py",
        "orchestrator/runtime/confirmation.py",
        "orchestrator/runtime/conversation_state.py",
        "orchestrator/runtime/session.py",
        "shared/chromie_contracts/semantic_task.py",
        "shared/chromie_contracts/perception.py",
    )
    strict_no_regex_paths = {
        "agent/app/agents/conversation.py",
        "agent/app/agents/capability.py",
        "agent/app/capabilities/catalog.py",
        "agent/app/capabilities/validator.py",
        "orchestrator/runtime/confirmation.py",
        "orchestrator/runtime/conversation_state.py",
        "shared/chromie_contracts/semantic_task.py",
    }
    forbidden_name_fragments = (
        "phrase",
        "keyword",
        "action_claim",
        "stage_direction",
        "confirmation_words",
        "reply_words",
        "question_form",
        "suffix_match",
        "greeting_semantics",
        "internal_narration",
        "failure_speech",
    )
    for relative in semantic_rule_paths:
        path = root / relative
        if not path.is_file():
            continue
        tree, parse_findings = _parse_python(path, root)
        findings.extend(parse_findings)
        if tree is None:
            continue
        if relative in strict_no_regex_paths:
            for module_name, node in _imported_module_names(tree):
                if module_name.split(".", 1)[0] in {"re", "regex"}:
                    findings.append(
                        PolicyFinding(
                            rule_id=RULE_HOST_SEMANTIC_AUTHORITY,
                            path=relative,
                            line=getattr(node, "lineno", 0) or 0,
                            symbol="<module>",
                            message=(
                                "semantic owner may not import regex; move mechanical "
                                "parsing to its contract owner and language meaning to the model"
                            ),
                        )
                    )
        seen_names: set[tuple[str, int]] = set()
        for node in ast.walk(tree):
            candidate_name = ""
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                candidate_name = node.name
            elif isinstance(node, ast.Name) and isinstance(
                node.ctx, (ast.Store, ast.Param)
            ):
                candidate_name = node.id
            lowered = candidate_name.casefold()
            if not candidate_name or not any(
                fragment in lowered for fragment in forbidden_name_fragments
            ):
                continue
            key = (candidate_name, getattr(node, "lineno", 0) or 0)
            if key in seen_names:
                continue
            seen_names.add(key)
            findings.append(
                PolicyFinding(
                    rule_id=RULE_HOST_SEMANTIC_AUTHORITY,
                    path=relative,
                    line=key[1],
                    symbol=candidate_name,
                    message=(
                        "ordinary language meaning may not be implemented as a "
                        "phrase, keyword, or speech-pattern rule"
                    ),
                )
            )

    memory_path = root / "agent/app/agents/memory.py"
    tree = None
    if memory_path.is_file():
        tree, parse_findings = _parse_python(memory_path, root)
        findings.extend(parse_findings)
    if tree is not None:
        for module_name, node in _imported_module_names(tree):
            if module_name.split(".", 1)[0] in {"re", "regex"}:
                findings.append(
                    PolicyFinding(
                        rule_id=RULE_MEMORY_MODEL_AUTHORED,
                        path=_relative(memory_path, root),
                        line=getattr(node, "lineno", 0) or 0,
                        symbol="<module>",
                        message="MemoryAgent may not use regex or phrase classification",
                    )
                )
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and _attribute_chain(node) == "request.text":
                findings.append(
                    PolicyFinding(
                        rule_id=RULE_MEMORY_MODEL_AUTHORED,
                        path=_relative(memory_path, root),
                        line=node.lineno,
                        symbol="MemoryAgent.run",
                        message="MemoryAgent must consume the typed model proposal, not infer semantics from raw text",
                    )
                )
        if not any(
            isinstance(node, ast.Attribute) and node.attr == "memory_update"
            for node in ast.walk(tree)
        ):
            findings.append(
                _source_policy_finding(
                    root=root,
                    path=_relative(memory_path, root),
                    rule_id=RULE_MEMORY_MODEL_AUTHORED,
                    symbol="MemoryAgent.run",
                    message="MemoryAgent must consume a typed memory_update proposal",
                )
            )
    return findings


def _base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _attribute_chain(node)
    return ""


def audit_canonical_capability_identity(root: Path) -> list[PolicyFinding]:
    """Enforce canonical executable Capability vocabulary.

    Agent Skills and provider-local wire protocols are separate namespaces. This
    rule protects Chromie-owned model/runtime/evidence contracts from reviving
    the retired executable ``Skill*`` API or ``skill_id`` compatibility fields.
    """

    targets = {
        "shared/chromie_contracts/social_attention.py": {
            "SocialAttentionBehavior": "CapabilityIdentityModel",
        },
        "orchestrator/runtime/episode.py": {
            "EpisodeCapabilityRequestRecord": "CapabilityIdentityModel",
            "EpisodeCapabilityResultRecord": "CapabilityIdentityModel",
        },
        "orchestrator/runtime/capability_runtime.py": {
            "CapabilityRuntimeEvent": "CapabilityIdentityModel",
        },
    }
    findings: list[PolicyFinding] = []
    for retired_relative in (
        "shared/chromie_contracts/task_proposal.py",
        "orchestrator/runtime/task_proposals.py",
    ):
        if (root / retired_relative).exists():
            findings.append(
                _source_policy_finding(
                    root=root,
                    path=retired_relative,
                    rule_id=RULE_CANONICAL_CAPABILITY_ID,
                    message=(
                        "retired TaskProposal compatibility contract must not be "
                        "reintroduced; CanonicalPlan/preflight/CapabilityRuntime/Evidence "
                        "are the maintained execution truth chain"
                    ),
                )
            )
    for relative, classes in targets.items():
        path = root / relative
        tree, parse_findings = _parse_python(path, root)
        findings.extend(parse_findings)
        if tree is None:
            continue
        class_nodes = {
            node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }
        for class_name, expected_base in classes.items():
            node = class_nodes.get(class_name)
            if node is None:
                findings.append(
                    _source_policy_finding(
                        root=root,
                        path=relative,
                        rule_id=RULE_CANONICAL_CAPABILITY_ID,
                        symbol=class_name,
                        message="canonical model/evidence contract is missing",
                    )
                )
                continue
            bases = {_base_name(base).rsplit(".", 1)[-1] for base in node.bases}
            if expected_base not in bases:
                findings.append(
                    PolicyFinding(
                        rule_id=RULE_CANONICAL_CAPABILITY_ID,
                        path=relative,
                        line=node.lineno,
                        symbol=class_name,
                        message=(
                            f"must inherit {expected_base} so canonical output uses "
                            "capability_id"
                        ),
                    )
                )
            for field_name, field_node in _class_field_names(node):
                if field_name in {"skill_id", "skill_version"}:
                    findings.append(
                        PolicyFinding(
                            rule_id=RULE_CANONICAL_CAPABILITY_ID,
                            path=relative,
                            line=getattr(field_node, "lineno", 0) or 0,
                            symbol=f"{class_name}.{field_name}",
                            message=(
                                "Chromie executable contracts must declare "
                                "capability_id/capability_version, not executable Skill aliases"
                            ),
                        )
                    )

    cancellation_path = root / "shared/chromie_contracts/reflex.py"
    cancellation_tree, parse_findings = _parse_python(cancellation_path, root)
    findings.extend(parse_findings)
    if cancellation_tree is not None:
        receipt = next(
            (
                node
                for node in ast.walk(cancellation_tree)
                if isinstance(node, ast.ClassDef)
                and node.name == "CancellationDispatchReceipt"
            ),
            None,
        )
        if receipt is None:
            findings.append(
                _source_policy_finding(
                    root=root,
                    path="shared/chromie_contracts/reflex.py",
                    rule_id=RULE_CANONICAL_CAPABILITY_ID,
                    symbol="CancellationDispatchReceipt",
                    message="canonical cancellation receipt contract is missing",
                )
            )
        else:
            fields = {name for name, _ in _class_field_names(receipt)}
            retired_unqualified_fields = {
                "selected_request_ids",
                "active_request_ids",
                "queued_request_ids",
                "cancel_requested_request_ids",
                "non_interruptible_request_ids",
                "shared_owner_conflict_request_ids",
                "stale_binding_request_ids",
                "provider_cancel_failures",
            }
            for field_name in sorted(fields.intersection(retired_unqualified_fields)):
                findings.append(
                    _source_policy_finding(
                        root=root,
                        path="shared/chromie_contracts/reflex.py",
                        rule_id=RULE_CANONICAL_CAPABILITY_ID,
                        symbol=f"CancellationDispatchReceipt.{field_name}",
                        message=(
                            "async cancellation identity must remain interaction-qualified; "
                            "do not reintroduce bare request-ID compatibility fields"
                        ),
                    )
                )
            required_binding_fields = {
                "selected_request_bindings",
                "active_request_bindings",
                "queued_request_bindings",
                "cancel_requested_request_bindings",
                "non_interruptible_request_bindings",
                "shared_owner_conflict_request_bindings",
                "stale_binding_request_bindings",
                "provider_cancel_failure_evidence",
            }
            for field_name in sorted(required_binding_fields - fields):
                findings.append(
                    _source_policy_finding(
                        root=root,
                        path="shared/chromie_contracts/reflex.py",
                        rule_id=RULE_CANONICAL_CAPABILITY_ID,
                        symbol=f"CancellationDispatchReceipt.{field_name}",
                        message=(
                            "canonical cancellation receipt must preserve exact "
                            "interaction-qualified runtime identity"
                        ),
                    )
                )

    runtime_path = root / "orchestrator/runtime/capability_runtime.py"
    if runtime_path.is_file():
        runtime_tree, parse_findings = _parse_python(runtime_path, root)
        findings.extend(parse_findings)
        if runtime_tree is not None:
            runtime_class = next(
                (
                    node
                    for node in ast.walk(runtime_tree)
                    if isinstance(node, ast.ClassDef) and node.name == "CapabilityRuntime"
                ),
                None,
            )
            if runtime_class is not None:
                method_names = {
                    node.name
                    for node in runtime_class.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                if "execute" in method_names:
                    findings.append(
                        _source_policy_finding(
                            root=root,
                            path="orchestrator/runtime/capability_runtime.py",
                            rule_id=RULE_CANONICAL_CAPABILITY_ID,
                            symbol="CapabilityRuntime.execute",
                            message=(
                                "retired aggregate CapabilityRuntime.execute API must not be "
                                "reintroduced; use submit() and lifecycle/terminal consumers"
                            ),
                        )
                    )
                for required_method in (
                    "submit",
                    "wait_terminal",
                    "runtime_events_after",
                    "wait_runtime_event",
                ):
                    if required_method not in method_names:
                        findings.append(
                            _source_policy_finding(
                                root=root,
                                path="orchestrator/runtime/capability_runtime.py",
                                rule_id=RULE_CANONICAL_CAPABILITY_ID,
                                symbol=f"CapabilityRuntime.{required_method}",
                                message=(
                                    "canonical CapabilityRuntime dispatch/completion boundary is missing"
                                ),
                            )
                        )

            retired_manager_names = {
                "WorkManager",
                "AsyncManager",
                "ResultManager",
                "EventManager",
                "ResultAgent",
                "AsyncAgent",
            }
            for class_node in (
                node for node in ast.walk(runtime_tree) if isinstance(node, ast.ClassDef)
            ):
                if class_node.name in retired_manager_names:
                    findings.append(
                        PolicyFinding(
                            rule_id=RULE_CANONICAL_CAPABILITY_ID,
                            path="orchestrator/runtime/capability_runtime.py",
                            line=class_node.lineno,
                            symbol=class_node.name,
                            message=(
                                "Capability Runtime lifecycle/events must remain Runtime-owned; "
                                "do not reintroduce a parallel manager/agent authority"
                            ),
                        )
                    )

    coordinator_path = root / "orchestrator/runtime/interaction_coordinator.py"
    if coordinator_path.is_file():
        coordinator_tree, parse_findings = _parse_python(coordinator_path, root)
        findings.extend(parse_findings)
        if coordinator_tree is not None:
            coordinator_class = next(
                (
                    node
                    for node in ast.walk(coordinator_tree)
                    if isinstance(node, ast.ClassDef)
                    and node.name == "InteractionRuntimeCoordinator"
                ),
                None,
            )
            coordinator_methods = {
                node.name
                for node in (coordinator_class.body if coordinator_class else [])
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if "execute" in coordinator_methods:
                findings.append(
                    _source_policy_finding(
                        root=root,
                        path="orchestrator/runtime/interaction_coordinator.py",
                        rule_id=RULE_CANONICAL_CAPABILITY_ID,
                        symbol="InteractionRuntimeCoordinator.execute",
                        message=(
                            "retired aggregate coordinator execute API must not be "
                            "reintroduced; use submit_response() and explicit consumers"
                        ),
                    )
                )
            for required_method in (
                "submit_response",
                "wait_dispatch",
            ):
                if required_method not in coordinator_methods:
                    findings.append(
                        _source_policy_finding(
                            root=root,
                            path="orchestrator/runtime/interaction_coordinator.py",
                            rule_id=RULE_CANONICAL_CAPABILITY_ID,
                            symbol=f"InteractionRuntimeCoordinator.{required_method}",
                            message=(
                                "capability execution must keep dispatch separate from "
                                "terminal consumers"
                            ),
                        )
                    )

    orchestrator_path = root / "orchestrator/orchestrator.py"
    if orchestrator_path.is_file():
        orchestrator_tree, parse_findings = _parse_python(orchestrator_path, root)
        findings.extend(parse_findings)
        if orchestrator_tree is not None:
            assistant_class = next(
                (
                    node
                    for node in ast.walk(orchestrator_tree)
                    if isinstance(node, ast.ClassDef) and node.name == "VoiceAssistant"
                ),
                None,
            )
            assistant_methods = {
                node.name
                for node in (assistant_class.body if assistant_class else [])
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if "execute_interaction_response" in assistant_methods:
                findings.append(
                    _source_policy_finding(
                        root=root,
                        path="orchestrator/orchestrator.py",
                        rule_id=RULE_CANONICAL_CAPABILITY_ID,
                        symbol="VoiceAssistant.execute_interaction_response",
                        message=(
                            "retired foreground aggregate interaction API must not be "
                            "reintroduced; all launches use detached Runtime dispatch"
                        ),
                    )
                )
            for required_method in (
                "_dispatch_detached_interaction",
                "_consume_detached_non_cognitive_dispatch",
                "_consume_detached_cognitive_dispatch",
                "_reenter_cognition_for_terminal_capability",
            ):
                if required_method not in assistant_methods:
                    findings.append(
                        _source_policy_finding(
                            root=root,
                            path="orchestrator/orchestrator.py",
                            rule_id=RULE_CANONICAL_CAPABILITY_ID,
                            symbol=f"VoiceAssistant.{required_method}",
                            message=(
                                "cognitive Capability lifetime must remain detached from "
                                "the foreground interaction call stack"
                            ),
                        )
                    )

    for relative in (
        "orchestrator/runtime/capability_runtime.py",
        "orchestrator/runtime/interaction_coordinator.py",
    ):
        path = root / relative
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        if "async def cancel_all(" in source:
            findings.append(
                _source_policy_finding(
                    root=root,
                    path=relative,
                    rule_id=RULE_CANONICAL_CAPABILITY_ID,
                    symbol="cancel_all",
                    message=(
                        "Capability cancellation must remain scope-qualified through "
                        "CancellationDirective/cancel_scope; broad cancel_all compatibility "
                        "must not be reintroduced"
                    ),
                )
            )

    retired_runtime_paths = (
        "orchestrator/runtime/abilities.py",
        "orchestrator/runtime/skill_runtime.py",
        "orchestrator/runtime/skill_adapters.py",
        "orchestrator/runtime/soridormi_skill_provider.py",
    )
    for relative in retired_runtime_paths:
        if (root / relative).exists():
            findings.append(
                _source_policy_finding(
                    root=root,
                    path=relative,
                    rule_id=RULE_CANONICAL_CAPABILITY_ID,
                    symbol="<retired-runtime-path>",
                    message=(
                        "retired duplicate runtime/ability authority module must not exist; "
                        "Planner + live Capability Registry own executable HOW/availability"
                    ),
                )
            )

    # These are Chromie-owned executable/runtime sources. Agent Skill code and
    # Soridormi wire payload strings are intentionally not scanned as aliases.
    retired_symbols = (
        "SkillRuntime",
        "SkillDefinition",
        "SkillRegistry",
        "SkillProvider",
        "SkillRequest",
        "SkillResult",
        "SkillTrace",
        "TrustedCapabilityRuntime",
    )
    canonical_runtime_files = (
        "shared/chromie_contracts/interaction.py",
        "shared/chromie_contracts/__init__.py",
        "orchestrator/runtime/capability_runtime.py",
        "orchestrator/runtime/capability_adapters.py",
        "orchestrator/runtime/interaction_coordinator.py",
        "orchestrator/runtime/outcome_reconciliation.py",
        "orchestrator/runtime/interaction_preflight.py",
        "orchestrator/runtime/episode.py",
        "orchestrator/runtime/experience.py",
        "orchestrator/runtime/task_proposals.py",
        "agent/app/agents/capability.py",
        "agent/app/agents/deepthinking.py",
        "agent/app/fast_planner.py",
        "agent/app/deep_planner.py",
        "agent/app/planner_contract.py",
    )
    for relative in canonical_runtime_files:
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for token in retired_symbols:
            if re.search(rf"\b{re.escape(token)}\b", text):
                findings.append(
                    _source_policy_finding(
                        root=root,
                        path=relative,
                        rule_id=RULE_CANONICAL_CAPABILITY_ID,
                        symbol=token,
                        message=(
                            "Chromie canonical executable runtime must not expose "
                            "retired executable-Skill symbols"
                        ),
                    )
                )

    canonical_source_checks = {
        "agent/app/fast_planner.py": (
            "FINAL ALLOWED EXECUTABLE SKILL IDS",
            "exact supplied skill IDs",
            "Skills are plan leaves",
        ),
        "agent/app/deep_planner.py": (
            "step_id, skill_id",
            "FINAL ALLOWED EXECUTABLE SKILL IDS",
            "Skills are plan leaves",
        ),
        "agent/app/agents/deepthinking.py": (
            'item["skill_id"]',
            'item.get("skill_id")',
        ),
        "orchestrator/runtime/cognitive_runtime.py": (
            '"skill_id": step.',
            '"skill_id": request.',
            '"skill_ids":',
        ),
        "orchestrator/runtime/experience.py": (
            '"skill_id": result.',
        ),
        "orchestrator/runtime/interaction_preflight.py": (
            '"skill_id": request.',
        ),
        "orchestrator/runtime/interaction_coordinator.py": (
            '"suppressed_skill_ids"',
        ),
        "orchestrator/runtime/task_proposals.py": (
            'proposal["skill_id"]',
            'proposal.get("skill_id")',
        ),
        "orchestrator/runtime/conversation_state.py": (
            '"skill_id": "chromie.speak"',
        ),
    }
    for relative, tokens in canonical_source_checks.items():
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if token in text:
                findings.append(
                    _source_policy_finding(
                        root=root,
                        path=relative,
                        rule_id=RULE_CANONICAL_CAPABILITY_ID,
                        symbol=token,
                        message=(
                            "current model, trace, API, and evidence output must use "
                            "canonical capability_id/capability_ids"
                        ),
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
    findings.extend(audit_semantic_authority_boundaries(root))
    findings.extend(audit_canonical_capability_identity(root))
    findings.extend(
        PolicyFinding(
            rule_id=RULE_UNCLASSIFIED_BROAD_EXCEPTION,
            path=item.path,
            line=item.line,
            symbol=item.symbol,
            message=item.message,
        )
        for item in audit_runtime_exception_boundaries(root)
    )
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
