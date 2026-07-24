from __future__ import annotations

import logging
from typing import Any

from ..clients.weather_client import (
    WeatherLookupError,
    WeatherQuery,
    WeatherReport,
    weather_code_text,
)
from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent

try:
    from chromie_contracts.tool_result import (
        ToolResultEvidence,
        ToolResultInterpretation,
        ToolResultInterpretationRequest,
        canonical_value_sha256,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.tool_result import (
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
                result.add_speak_immediate(
                    "我已经准备好一个执行计划。" if self.is_zh(request) else "I prepared a task plan.",
                    style="brief",
                )
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

        if self._is_weather_request(request) and self.services.weather_client is not None:
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
        if not result.speak_immediate:
            result.add_speak_immediate("我看一下。" if self.is_zh(request) else "Let me check.", style="brief")
        self.trace(result, f"planned tool.{intent}")
        return result

    def _is_weather_request(self, request: AgentRunRequest) -> bool:
        decision = request.route_decision
        intent = str(decision.intent or "").casefold()
        metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
        if str(metadata.get("tool_name") or "").casefold() == "weather":
            return True
        if isinstance(metadata.get("weather_query"), dict):
            return True
        if "weather" in intent or "forecast" in intent:
            return True
        for item in decision.routes or []:
            item_intent = str(item.intent or "").casefold()
            item_metadata = item.metadata if isinstance(item.metadata, dict) else {}
            if item.route == "tool" and ("weather" in item_intent or "forecast" in item_intent):
                return True
            if str(item_metadata.get("tool_name") or "").casefold() == "weather":
                return True
            if isinstance(item_metadata.get("weather_query"), dict):
                return True
        return False

    async def _run_weather(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        zh = self.is_zh(request)
        client = self.services.weather_client
        logger.info(
            "weather_tool_start sid=%s language=%s has_client=%s",
            request.sid,
            self.language(request),
            client is not None,
        )
        if client is None:
            result.add_speak_immediate(
                "我现在还没有启用天气查询工具。" if zh else "I do not have the weather lookup tool enabled right now.",
                style="warning",
            )
            self.trace(result, "weather tool unavailable")
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
            result.add_speak_immediate(
                "你想查哪个城市的天气？" if zh else "Which city should I check the weather for?",
                style="brief",
            )
            self.trace(result, "weather query needs location clarification")
            return result

        try:
            logger.info("weather_lookup_start sid=%s location=%r date=%s", request.sid, query.location, query.date)
            report = await client.lookup(query)
        except WeatherLookupError as exc:
            logger.info(
                "weather_tool_failed sid=%s reason=lookup_error location=%r error=%s",
                request.sid,
                query.location,
                exc,
            )
            result.add_speak_immediate(
                f"我没查到这个地点的天气：{query.location}。" if zh else f"I could not find weather for {query.location}.",
                style="warning",
            )
            self.trace(result, f"weather lookup failed: {exc}")
            return result
        except Exception as exc:
            logger.warning(
                "weather_lookup_failed sid=%s location=%r error_type=%s error=%s",
                request.sid,
                query.location,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            result.add_speak_immediate(
                "我现在连不上天气服务，稍后再试一下。" if zh else "I cannot reach the weather service right now. Please try again later.",
                style="warning",
            )
            self.trace(result, f"weather service error: {type(exc).__name__}")
            return result

        logger.info(
            "weather_lookup_done sid=%s location=%r source=%s date=%r temp_c=%s high_c=%s low_c=%s code=%s",
            request.sid,
            report.location_name,
            report.source,
            report.date,
            report.current_temperature_c,
            report.daily_high_c,
            report.daily_low_c,
            report.weather_code,
        )
        spoken_response, evidence, interpretation = await self._compose_weather_response(
            request,
            query=query,
            report=report,
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
            f"location={report.location_name!r} source={report.source} date={report.date!r}"
        )
        result.handled_by.append(self.name)
        return result

    async def _compose_weather_response(
        self,
        request: AgentRunRequest,
        *,
        query: WeatherQuery,
        report: WeatherReport,
    ) -> tuple[str, ToolResultEvidence, ToolResultInterpretation]:
        fallback = self._brief_weather_fallback(
            report,
            language=self.language(request),
            units=query.units,
        )
        report_payload = {
            "location_name": report.location_name,
            "date": report.date,
            "condition": weather_code_text(
                report.weather_code,
                zh=self.is_zh(request),
            ),
            "current_temperature_c": report.current_temperature_c,
            "apparent_temperature_c": report.apparent_temperature_c,
            "daily_high_c": report.daily_high_c,
            "daily_low_c": report.daily_low_c,
            "precipitation_probability_max": report.precipitation_probability_max,
            "precipitation_sum_mm": report.precipitation_sum_mm,
            "wind_speed_kmh": report.wind_speed_kmh,
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

    @staticmethod
    def _brief_weather_fallback(
        report: WeatherReport,
        *,
        language: str,
        units: str,
    ) -> str:
        """Bounded grounded fallback when semantic composition is unavailable."""

        zh = language.lower().startswith("zh")
        imperial = units == "imperial"

        def temperature(value: float | None) -> float | None:
            if value is None:
                return None
            return value * 9.0 / 5.0 + 32.0 if imperial else value

        current = temperature(report.current_temperature_c)
        apparent = temperature(report.apparent_temperature_c)
        high = temperature(report.daily_high_c)
        unit = "℉" if imperial else "℃"
        unit_en = "°F" if imperial else "°C"
        condition = weather_code_text(report.weather_code, zh=zh)

        if zh:
            facts: list[str] = []
            if current is not None:
                facts.append(f"现在{current:.0f}{unit}")
            if apparent is not None and (
                current is None or abs(apparent - current) >= 2.0
            ):
                facts.append(f"体感{apparent:.0f}{unit}")
            if high is not None:
                facts.append(f"最高{high:.0f}{unit}")
            suffix = "，".join(facts[:3])
            return (
                f"{report.location_name}今天{condition}，{suffix}。"
                if suffix
                else f"{report.location_name}今天{condition}。"
            )

        facts = []
        if current is not None:
            facts.append(f"{current:.0f}{unit_en} now")
        if apparent is not None and (
            current is None or abs(apparent - current) >= 3.0
        ):
            facts.append(f"feels like {apparent:.0f}{unit_en}")
        if high is not None:
            facts.append(f"high {high:.0f}{unit_en}")
        suffix = ", ".join(facts[:3])
        return (
            f"Today in {report.location_name}: {condition}, {suffix}."
            if suffix
            else f"Today in {report.location_name}: {condition}."
        )

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
                    response_format="json",
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
        normalized = str(value or "today").strip().casefold().replace("_", "-")
        if normalized in {"tomorrow", "next-day", "next day", "明天"}:
            return "tomorrow"
        return "today"

    @staticmethod
    def _normalize_units(value: Any) -> str:
        normalized = str(value or "metric").strip().casefold()
        if normalized in {"imperial", "fahrenheit", "f"}:
            return "imperial"
        if normalized in {"auto"}:
            return "auto"
        return "metric"

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
