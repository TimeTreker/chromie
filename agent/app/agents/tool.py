from __future__ import annotations

import logging
from typing import Any

from ..clients.weather_client import (
    WeatherLookupError,
    WeatherQuery,
    format_weather_report,
)
from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent

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
        result.add_speak_immediate(
            format_weather_report(report, language=self.language(request), units=query.units),
            style="brief",
        )
        result.trace.append(
            "tool_agent: weather_lookup_completed "
            f"location={report.location_name!r} source={report.source} date={report.date!r}"
        )
        result.handled_by.append(self.name)
        return result

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
