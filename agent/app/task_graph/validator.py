from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..capabilities.models import CapabilityRegistry, ToolCapability

from .models import TaskGraph, TaskNode
from .refs import iter_refs, ref_node_id


@dataclass
class GraphValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def raise_for_errors(self) -> None:
        if self.errors:
            raise ValueError("TaskGraph validation failed: " + "; ".join(self.errors))


class GraphValidator:
    """Validate an LLM-proposed TaskGraph against Chromie's global registry."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def validate(self, graph: TaskGraph) -> GraphValidationReport:
        report = GraphValidationReport()
        nodes = graph.node_map()
        self._validate_node_refs(graph, nodes, report)
        self._validate_tools(graph, report)
        self._validate_args(graph, report)
        self._validate_fallbacks(graph, nodes, report)
        self._validate_refs(graph, nodes, report)
        self._validate_cycles(graph, nodes, report)
        self._validate_physical_motion(graph, nodes, report)
        return report

    def _validate_node_refs(self, graph: TaskGraph, nodes: dict[str, TaskNode], report: GraphValidationReport) -> None:
        for node in graph.nodes:
            for dep in node.depends_on:
                if dep not in nodes:
                    report.errors.append(f"node {node.id!r} depends on unknown node {dep!r}")
            for running in node.during:
                if running not in nodes:
                    report.errors.append(f"monitor node {node.id!r} references unknown during node {running!r}")

    def _validate_tools(self, graph: TaskGraph, report: GraphValidationReport) -> None:
        for node in graph.nodes:
            try:
                tool = self.registry.get_tool(node.tool)
            except KeyError:
                report.errors.append(f"node {node.id!r} uses unknown tool {node.tool!r}")
                continue
            if graph.created_by == "llm" and not tool.llm_visible:
                report.errors.append(f"LLM graph may not call hidden tool {node.tool!r}")
            if graph.created_by == "llm" and tool.safety_class == "restricted":
                report.errors.append(f"LLM graph may not call restricted tool {node.tool!r}")
            if not tool.availability.available:
                reason = tool.availability.reason or "unavailable"
                report.errors.append(f"tool {node.tool!r} is unavailable: {reason}")
            if node.timeout_s is not None and tool.execution.timeout_s is not None and node.timeout_s > tool.execution.timeout_s:
                report.errors.append(
                    f"node {node.id!r} timeout {node.timeout_s}s exceeds tool default {tool.execution.timeout_s}s"
                )

    def _validate_args(self, graph: TaskGraph, report: GraphValidationReport) -> None:
        for node in graph.nodes:
            try:
                tool = self.registry.get_tool(node.tool)
            except KeyError:
                continue
            self._validate_value_against_schema(node.id, "args", node.args, tool.input_schema, report)

    def _validate_value_against_schema(
        self,
        node_id: str,
        path: str,
        value: Any,
        schema: dict[str, Any],
        report: GraphValidationReport,
    ) -> None:
        if not schema:
            return
        if isinstance(value, dict) and set(value.keys()) == {"$ref"}:
            return
        schema_type = schema.get("type")
        if isinstance(schema_type, list):
            schema_types = schema_type
        elif schema_type:
            schema_types = [schema_type]
        else:
            schema_types = []

        if schema_types and not self._matches_any_type(value, schema_types):
            report.errors.append(f"node {node_id!r} {path} expected type {schema_types}, got {type(value).__name__}")
            return

        if "minimum" in schema and isinstance(value, (int, float)) and value < schema["minimum"]:
            report.errors.append(f"node {node_id!r} {path} is below minimum {schema['minimum']}")
        if "maximum" in schema and isinstance(value, (int, float)) and value > schema["maximum"]:
            report.errors.append(f"node {node_id!r} {path} exceeds maximum {schema['maximum']}")
        if "enum" in schema and value not in schema["enum"]:
            report.errors.append(f"node {node_id!r} {path} must be one of {schema['enum']}")

        if schema_type == "object" or (not schema_type and "properties" in schema):
            if not isinstance(value, dict):
                report.errors.append(f"node {node_id!r} {path} expected object")
                return
            required = schema.get("required", [])
            for key in required:
                if key not in value:
                    report.errors.append(f"node {node_id!r} missing required arg {path}.{key}")
            properties = schema.get("properties", {})
            for key, child in value.items():
                if key in properties:
                    self._validate_value_against_schema(node_id, f"{path}.{key}", child, properties[key], report)
        elif schema_type == "array":
            if not isinstance(value, list):
                report.errors.append(f"node {node_id!r} {path} expected array")
                return
            if "minItems" in schema and len(value) < schema["minItems"]:
                report.errors.append(f"node {node_id!r} {path} has fewer than {schema['minItems']} items")
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                report.errors.append(f"node {node_id!r} {path} has more than {schema['maxItems']} items")
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for idx, item in enumerate(value):
                    self._validate_value_against_schema(node_id, f"{path}[{idx}]", item, item_schema, report)

    def _matches_any_type(self, value: Any, schema_types: list[str]) -> bool:
        for schema_type in schema_types:
            if schema_type == "null" and value is None:
                return True
            if schema_type == "object" and isinstance(value, dict):
                return True
            if schema_type == "array" and isinstance(value, list):
                return True
            if schema_type == "string" and isinstance(value, str):
                return True
            if schema_type == "boolean" and isinstance(value, bool):
                return True
            if schema_type == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
                return True
            if schema_type == "integer" and isinstance(value, int) and not isinstance(value, bool):
                return True
        return False

    def _validate_fallbacks(self, graph: TaskGraph, nodes: dict[str, TaskNode], report: GraphValidationReport) -> None:
        for node in graph.nodes:
            for field_name, policy in (("on_failure", node.on_failure), ("on_timeout", node.on_timeout)):
                if policy and policy.strategy == "goto" and not policy.target:
                    report.errors.append(f"node {node.id!r} {field_name} goto policy must specify target")
                if policy and policy.target and policy.target not in nodes:
                    report.errors.append(f"node {node.id!r} {field_name} target {policy.target!r} does not exist")
            for event, policy in node.on_event.items():
                if policy.strategy == "goto" and not policy.target:
                    report.errors.append(f"node {node.id!r} event {event!r} goto policy must specify target")
                if policy.target and policy.target not in nodes:
                    report.errors.append(f"node {node.id!r} event {event!r} target {policy.target!r} does not exist")

    def _validate_refs(self, graph: TaskGraph, nodes: dict[str, TaskNode], report: GraphValidationReport) -> None:
        for node in graph.nodes:
            for ref in iter_refs(node.args):
                source = ref_node_id(ref)
                if source is None:
                    report.errors.append(f"node {node.id!r} has malformed ref {ref!r}; expected <node>.output.<field>")
                    continue
                if source not in nodes:
                    report.errors.append(f"node {node.id!r} refs unknown node {source!r}")
                elif source not in node.depends_on and node.id not in nodes[source].during:
                    report.warnings.append(f"node {node.id!r} refs {source!r} without an explicit dependency")

    def _validate_cycles(self, graph: TaskGraph, nodes: dict[str, TaskNode], report: GraphValidationReport) -> None:
        edges: dict[str, set[str]] = {node.id: set() for node in graph.nodes}
        for node in graph.nodes:
            for dep in node.depends_on:
                if dep in nodes:
                    edges[dep].add(node.id)
            for policy in (node.on_failure, node.on_timeout):
                if policy and policy.target in nodes:
                    edges[node.id].add(policy.target)
            for policy in node.on_event.values():
                if policy.target in nodes:
                    edges[node.id].add(policy.target)

        visiting: set[str] = set()
        visited: set[str] = set()

        def dfs(node_id: str, stack: list[str]) -> None:
            if node_id in visiting:
                cycle = " -> ".join(stack + [node_id])
                report.errors.append(f"task graph contains cycle: {cycle}")
                return
            if node_id in visited:
                return
            visiting.add(node_id)
            for child in edges.get(node_id, set()):
                dfs(child, stack + [node_id])
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in nodes:
            dfs(node_id, [])

    def _validate_physical_motion(self, graph: TaskGraph, nodes: dict[str, TaskNode], report: GraphValidationReport) -> None:
        confirmation_nodes = {node.id for node in graph.nodes if node.type == "confirmation" or node.tool == "chromie.ask_confirmation"}
        monitor_nodes = [node for node in graph.nodes if node.type == "monitor"]

        for node in graph.nodes:
            try:
                tool = self.registry.get_tool(node.tool)
            except KeyError:
                continue
            if tool.safety_class != "physical_motion" and "physical_motion" not in tool.effects:
                continue
            if tool.confirmation.required and not self._has_transitive_dependency(node.id, confirmation_nodes, nodes):
                report.errors.append(f"physical-motion node {node.id!r} must depend on a confirmation node")
            if tool.monitoring.requires_safety_monitor:
                has_monitor = any(node.id in monitor.during for monitor in monitor_nodes)
                if not has_monitor:
                    report.errors.append(f"physical-motion node {node.id!r} must be covered by a monitor node")
            if not node.on_failure and tool.default_failure_policy.strategy not in {"stop_and_report", "emergency_stop"}:
                report.warnings.append(f"physical-motion node {node.id!r} has no explicit safe failure policy")

    def _has_transitive_dependency(self, node_id: str, candidates: set[str], nodes: dict[str, TaskNode]) -> bool:
        seen: set[str] = set()

        def walk(current: str) -> bool:
            if current in seen or current not in nodes:
                return False
            seen.add(current)
            for dep in nodes[current].depends_on:
                if dep in candidates or walk(dep):
                    return True
            return False

        return walk(node_id)
