from __future__ import annotations

import logging
from typing import Any

from ..clients.weather_client import WeatherLocationContext, WeatherQuery
from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent

try:
    from chromie_contracts.tool_result import (
        ToolExecutionRequest,
        ToolResultEvidence,
        ToolResultInterpretation,
        ToolResultInterpretationRequest,
        canonical_value_sha256,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.tool_result import (
        ToolExecutionRequest,
        ToolResultEvidence,
        ToolResultInterpretation,
        ToolResultInterpretationRequest,
        canonical_value_sha256,
    )

logger = logging.getLogger("chromie.agent.tool")


class ToolAgent(BaseAgent):
    name = "tool_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        if request.route_decision.route != "tool" and self.name not in request.route_decision.agents:
            return result

        logger.info(
            "tool_agent_start sid=%s route=%s intent=%s agents=%s metadata_keys=%s",
            request.sid,
            request.route_decision.route,
            request.route_decision.intent,
            list(request.route_decision.agents),
            sorted(str(key) for key in (request.route_decision.metadata or {}).keys())
            if isinstance(request.route_decision.metadata, dict)
            else [],
        )
        planner = self.services.task_graph_planner
        if planner is not None and request.route_decision.route == "tool":
            try:
                graph = await planner.plan(
                    user_request=request.text,
                    language=self.language(request),
                    context=request.context,
                )
                result.add_task_graph(graph.model_dump(mode="json"))
                self.trace(result, f"planned TaskGraph {graph.graph_id} with {len(graph.nodes)} node(s)")
                return result
            except Exception as exc:
                logger.warning(
                    "task_graph_planning_failed sid=%s error_type=%s error=%s",
                    request.sid,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                result.trace.append(f"tool_agent: TaskGraph planning failed: {type(exc).__name__}: {exc}")

        if self._selects_weather_capability(request) and self.services.local_tool_executor is not None:
            logger.info(
                "tool_agent_dispatch sid=%s tool=weather intent=%s",
                request.sid,
                request.route_decision.intent,
            )
            return await self._run_weather(request, result)

        intent = request.route_decision.intent or "tool_request"
        result.add_action(
            "tool_executor",
            f"tool.{intent}",
            params={"text": request.text, "language": request.language, "context": request.context},
            blocking=True,
            timeout_ms=5000,
            reason="tool_request_planned_by_agent",
        )
        self.trace(result, f"planned tool.{intent}")
        return result

    @staticmethod
    def _selects_weather_capability(request: AgentRunRequest) -> bool:
        decision = request.route_decision
        selected_ids: set[str] = set()
        intent = str(decision.intent or "").strip()
        if intent.startswith("capability:"):
            selected_ids.add(intent.split(":", 1)[1].strip())
        for item in decision.routes or []:
            capability_id = str(item.capability_id or "").strip()
            if capability_id:
                selected_ids.add(capability_id)
            item_intent = str(item.intent or "").strip()
            if item_intent.startswith("capability:"):
                selected_ids.add(item_intent.split(":", 1)[1].strip())
        return "chromie.weather.lookup" in selected_ids

    async def _run_weather(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        zh = self.is_zh(request)
        executor = self.services.local_tool_executor
        logger.info(
            "weather_tool_start sid=%s language=%s has_executor=%s",
            request.sid,
            self.language(request),
            executor is not None,
        )
        if executor is None:
            result.status = "error"
            result.reason = "weather_capability_executor_unavailable"
            result.add_speak_immediate(
                self.invalid_spoken_response_fallback(zh=zh),
                style="warning",
            )
            self.trace(result, "weather capability executor unavailable")
            return result

        query = await self._extract_weather_query(request)
        logger.info(
            "weather_request_params sid=%s location=%r date=%s units=%s language=%s",
            request.sid,
            query.location,
            query.date,
            query.units,
            query.language,
        )
        if not query.location:
            result.status = "clarify"
            result.reason = "weather_location_binding_missing"
            result.metadata["information_gaps"] = [
                {
                    "field": "location",
                    "reason": "authoritative Goal binding is missing",
                }
            ]
            self.trace(result, "weather query needs model-authored location binding")
            return result

        execution = await executor.execute(
            ToolExecutionRequest(
                request_id=f"weather-{request.sid or 'turn'}",
                tool_id="chromie.weather.lookup",
                args={
                    "location": query.location,
                    "date": query.date,
                    "units": query.units,
                    **(
                        {"location_context": query.location_context.model_dump(mode="json", exclude_none=True)}
                        if query.location_context is not None
                        else {}
                    ),
                },
                correlation_id=request.sid or "",
                language=self.language(request),
            )
        )
        if execution.status != "completed":
            logger.info(
                "weather_tool_failed sid=%s status=%s reason=%s location=%r",
                request.sid,
                execution.status,
                execution.reason_code,
                query.location,
            )
            result.status = "error"
            result.reason = execution.reason_code or execution.status
            result.metadata.setdefault("tool_results", []).append(
                {
                    "tool_id": "chromie.weather.lookup",
                    "status": execution.status,
                    "reason_code": execution.reason_code,
                    "location": query.location,
                }
            )
            result.add_speak_immediate(
                self.invalid_spoken_response_fallback(zh=zh),
                style="warning",
            )
            self.trace(
                result,
                f"weather lookup failed: status={execution.status} reason={execution.reason_code}",
            )
            return result

        output = dict(execution.output)
        logger.info(
            "weather_lookup_done sid=%s location=%r source=%s date=%r temp_c=%s high_c=%s low_c=%s code=%s",
            request.sid,
            output.get("location"),
            output.get("source"),
            output.get("date"),
            output.get("current_temperature_c"),
            output.get("high_c"),
            output.get("low_c"),
            output.get("weather_code"),
        )
        spoken_response, evidence, interpretation = await self._compose_weather_response(
            request,
            query=query,
            output=output,
        )
        result.add_speak_immediate(spoken_response, style="brief")
        result.metadata.setdefault("tool_results", []).append(
            {
                "tool_id": evidence.tool_id,
                "evidence_id": evidence.evidence_id,
                "status": evidence.status,
                "data": evidence.data,
                "output_sha256": evidence.output_sha256,
            }
        )
        result.metadata["tool_result_interpretation"] = interpretation.model_dump(
            mode="json"
        )
        result.trace.append(
            "tool_agent: weather_lookup_completed "
            f"location={output.get('location')!r} source={output.get('source')} date={output.get('date')!r}"
        )
        result.handled_by.append(self.name)
        return result

    async def _compose_weather_response(
        self,
        request: AgentRunRequest,
        *,
        query: WeatherQuery,
        output: dict[str, Any],
    ) -> tuple[str, ToolResultEvidence, ToolResultInterpretation]:
        fallback = str(output.get("summary") or "").strip()
        report_payload = {
            "location_name": output.get("location"),
            "date": output.get("date"),
            "condition": output.get("condition"),
            "current_temperature_c": output.get("current_temperature_c"),
            "apparent_temperature_c": output.get("apparent_temperature_c"),
            "daily_high_c": output.get("high_c"),
            "daily_low_c": output.get("low_c"),
            "precipitation_probability_max": output.get("precipitation_probability_max"),
            "precipitation_sum_mm": output.get("precipitation_sum_mm"),
            "wind_speed_kmh": output.get("wind_speed_kmh"),
            "requested_units": query.units,
        }
        evidence = ToolResultEvidence(
            evidence_id=f"weather_{request.sid or 'turn'}",
            tool_id="chromie.weather.lookup",
            status="completed",
            data=report_payload,
            output_sha256=canonical_value_sha256(report_payload),
        )
        interpreter = self.services.tool_result_interpreter
        if interpreter is None:
            interpretation = ToolResultInterpretation(
                status="fallback",
                spoken_response=fallback,
                answer_mode="summary",
                rationale="Tool result interpreter is disabled; trusted weather fallback used.",
                metadata={
                    "resolver": "tool_result_interpreter",
                    "fallback": True,
                    "reason": "interpreter_disabled",
                    "full_tool_result_retained": True,
                },
            )
            return fallback, evidence, interpretation

        mind = self.mind_context(request)
        identity = mind.get("identity") if isinstance(mind, dict) else None
        personality = (
            mind.get("personality_expression") if isinstance(mind, dict) else None
        )
        interpretation_request = ToolResultInterpretationRequest(
            sid=request.sid or "",
            user_request=request.text,
            language=self.language(request),
            evidence=[evidence],
            fallback_response=fallback,
            max_spoken_chars=48 if self.is_zh(request) else 180,
            detailed_max_spoken_chars=180 if self.is_zh(request) else 420,
            max_sentences=2,
            detailed_max_sentences=4,
            context={
                "route": request.route_decision.route,
                "intent": request.route_decision.intent,
                "identity": identity if isinstance(identity, dict) else {},
                "personality_expression": (
                    personality if isinstance(personality, dict) else {}
                ),
            },
        )
        interpretation = await interpreter.interpret(interpretation_request)
        spoken = interpretation.spoken_response or fallback
        logger.info(
            "weather_response_interpreted sid=%s chars=%s status=%s mode=%s selected_facts=%s",
            request.sid,
            len(spoken),
            interpretation.status,
            interpretation.answer_mode,
            len(interpretation.selected_facts),
        )
        return spoken, evidence, interpretation

    @staticmethod
    def _bounded_json(value: Any, max_chars: int) -> str:
        import json

        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return text if len(text) <= max_chars else text[:max_chars].rstrip() + "..."

    async def _extract_weather_query(self, request: AgentRunRequest) -> WeatherQuery:
        language = self.language(request)
        metadata_query = self._metadata_weather_query(request)
        location = str(metadata_query.get("location") or "").strip()
        date = self._normalize_date(metadata_query.get("date") or metadata_query.get("day"))
        units = self._normalize_units(metadata_query.get("units"))
        logger.info(
            "weather_query_extract_start sid=%s metadata_present=%s metadata_location=%r metadata_date=%s metadata_units=%s use_llm=%s",
            request.sid,
            bool(metadata_query),
            location,
            date,
            units,
            self.services.ollama is not None and self.services.use_llm,
        )

        if self.services.ollama is not None and self.services.use_llm:
            try:
                raw = await self.services.ollama.generate(
                    self._weather_extraction_prompt(request),
                    system=self._weather_extraction_system(),
                    options={"temperature": 0, "top_p": 0.9, "num_predict": 160},
                    response_format=self._weather_extraction_schema(),
                )
                if isinstance(raw, dict):
                    logger.info(
                        "weather_query_extract_llm_result sid=%s location=%r date=%s units=%s keys=%s",
                        request.sid,
                        raw.get("location"),
                        raw.get("date"),
                        raw.get("units"),
                        sorted(str(key) for key in raw.keys()),
                    )
                    location = str(raw.get("location") or location or "").strip()
                    date = self._normalize_date(raw.get("date") or date)
                    units = self._normalize_units(raw.get("units") or units)
            except Exception as exc:
                logger.warning(
                    "weather_query_extraction_failed sid=%s error_type=%s error=%s",
                    request.sid,
                    type(exc).__name__,
                    exc,
                )

        logger.info(
            "weather_query_extract_done sid=%s final_location=%r final_date=%s final_units=%s",
            request.sid,
            location,
            date,
            units,
        )
        return WeatherQuery(
            location=location,
            date=date,
            units=units,
            language=language,
            location_context=WeatherLocationContext.from_mapping(
                metadata_query.get("location_context")
            ),
        )

    def _metadata_weather_query(self, request: AgentRunRequest) -> dict[str, Any]:
        decision = request.route_decision
        metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
        query = metadata.get("weather_query")
        if isinstance(query, dict):
            return dict(query)
        for item in decision.routes or []:
            item_metadata = item.metadata if isinstance(item.metadata, dict) else {}
            query = item_metadata.get("weather_query")
            if isinstance(query, dict):
                return dict(query)
        return {}

    @staticmethod
    def _normalize_date(value: Any) -> str:
        normalized = str(value or "today").strip().casefold()
        return normalized if normalized in {"today", "tomorrow"} else "today"

    @staticmethod
    def _normalize_units(value: Any) -> str:
        normalized = str(value or "metric").strip().casefold()
        return normalized if normalized in {"metric", "imperial", "auto"} else "metric"

    @staticmethod
    def _weather_extraction_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["location", "date", "units"],
            "properties": {
                "location": {"type": "string"},
                "date": {"type": "string", "enum": ["today", "tomorrow"]},
                "units": {
                    "type": "string",
                    "enum": ["metric", "imperial", "auto"],
                },
            },
        }

    @staticmethod
    def _weather_extraction_system() -> str:
        return (
            "You extract parameters for a read-only weather lookup. Return JSON only. "
            "Do not answer the weather question. Do not invent a location that the user did not provide or context does not clearly supply."
        )

    def _weather_extraction_prompt(self, request: AgentRunRequest) -> str:
        route_metadata = request.route_decision.metadata if isinstance(request.route_decision.metadata, dict) else {}
        context = request.context if isinstance(request.context, dict) else {}
        return (
            "Extract a weather lookup request from the latest user input and compact route metadata.\n"
            "Fields:\n"
            "- location: city/place name string, or empty string when missing.\n"
            "- date: today or tomorrow.\n"
            "- units: metric, imperial, or auto.\n"
            "Return exactly: {\"location\":\"...\",\"date\":\"today\",\"units\":\"metric\"}\n\n"
            f"User language: {self.language(request)}\n"
            f"Latest user input: {request.text}\n"
            f"Route intent: {request.route_decision.intent}\n"
            f"Route metadata: {self._bounded_json(route_metadata, 1200)}\n"
            f"Context hints: {self._bounded_json(self._weather_context_hints(context), 1200)}"
        )

    @staticmethod
    def _weather_context_hints(context: dict[str, Any]) -> dict[str, Any]:
        hints: dict[str, Any] = {}
        for key in ("user_location", "location", "locale", "timezone"):
            if key in context:
                hints[key] = context[key]
        return hints
