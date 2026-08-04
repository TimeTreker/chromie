from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class ExternalInformationError(RuntimeError):
    """Raised when the configured external-information provider cannot return evidence."""

    def __init__(self, message: str, *, reason_code: str = "external_information_failed") -> None:
        super().__init__(" ".join(str(message or "").strip().split()))
        self.reason_code = " ".join(str(reason_code or "").strip().split())


@dataclass(frozen=True, slots=True)
class ExternalInformationQuery:
    question: str
    request_kind: str = "general_research"
    location: str = ""
    time_scope: str = ""
    freshness: str = "current"
    max_results: int = 8
    constraints: dict[str, Any] | None = None
    language: str = "en-US"

    def payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "question": " ".join(self.question.strip().split()),
            "request_kind": self.request_kind,
            "freshness": self.freshness,
            "max_results": self.max_results,
            "language": self.language,
        }
        if self.location.strip():
            payload["location"] = " ".join(self.location.strip().split())
        if self.time_scope.strip():
            payload["time_scope"] = " ".join(self.time_scope.strip().split())
        if self.constraints:
            payload["constraints"] = dict(self.constraints)
        return payload


class HttpExternalInformationClient:
    """Thin provider adapter for read-only grounded external information.

    The provider owns search, browsing, ranking, source access, and result
    normalization. This adapter sends one already-planned semantic request and
    returns evidence only; it does not compose Chromie's user-facing answer.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        timeout_s: float = 15.0,
        bearer_token: str = "",
    ) -> None:
        self.endpoint = endpoint.strip()
        if not self.endpoint:
            raise ValueError("external-information endpoint is required")
        self.timeout_s = max(0.1, float(timeout_s))
        self.bearer_token = bearer_token.strip()

    async def retrieve(self, query: ExternalInformationQuery) -> dict[str, Any]:
        payload = query.payload()
        if not payload["question"]:
            raise ExternalInformationError(
                "external-information request requires a question",
                reason_code="question_missing",
            )
        try:
            headers = (
                {"Authorization": f"Bearer {self.bearer_token}"}
                if self.bearer_token
                else None
            )
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.post(
                    self.endpoint,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                raw = response.json()
        except httpx.TimeoutException as exc:
            raise ExternalInformationError(
                "external-information provider timed out",
                reason_code="provider_timeout",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ExternalInformationError(
                f"external-information provider returned HTTP {exc.response.status_code}",
                reason_code="provider_http_error",
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ExternalInformationError(
                f"external-information provider failed: {type(exc).__name__}",
                reason_code="provider_error",
            ) from exc

        return self._normalize_result(raw, query=payload)

    @staticmethod
    def _normalize_result(raw: Any, *, query: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ExternalInformationError(
                "external-information provider returned a non-object result",
                reason_code="malformed_result",
            )
        summary = " ".join(str(raw.get("summary") or "").strip().split())
        if not summary:
            raise ExternalInformationError(
                "external-information provider returned no summary material",
                reason_code="empty_result",
            )
        items = raw.get("items")
        sources = raw.get("sources")
        if not isinstance(items, list):
            items = []
        if not isinstance(sources, list):
            sources = []
        normalized_sources: list[dict[str, Any]] = []
        for item in sources[:20]:
            if not isinstance(item, dict):
                continue
            title = " ".join(str(item.get("title") or "").strip().split())
            url = str(item.get("url") or "").strip()
            if not title and not url:
                continue
            normalized_sources.append(
                {
                    "title": title,
                    "url": url,
                    "published_at": item.get("published_at"),
                    "retrieved_at": item.get("retrieved_at"),
                }
            )
        if not normalized_sources:
            raise ExternalInformationError(
                "external-information provider returned no source evidence",
                reason_code="ungrounded_result",
            )
        retrieved_at = " ".join(
            str(raw.get("retrieved_at") or "").strip().split()
        )
        if not retrieved_at:
            raise ExternalInformationError(
                "external-information provider returned no retrieval timestamp",
                reason_code="retrieval_time_missing",
            )
        raw_query = raw.get("query")
        normalized_query = dict(raw_query) if isinstance(raw_query, dict) else dict(query)
        return {
            "query": normalized_query,
            "summary": summary,
            "items": [item for item in items[:20] if isinstance(item, dict)],
            "sources": normalized_sources,
            "retrieved_at": retrieved_at,
            "provider": " ".join(
                str(raw.get("provider") or "external_information").strip().split()
            ),
        }
