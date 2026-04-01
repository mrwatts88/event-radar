from __future__ import annotations

import logging
from datetime import date
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from event_radar.models import AIEventBatch, AIExtractedEvent


LOGGER = logging.getLogger(__name__)


def build_openai_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def schema_payload(model: type[BaseModel], name: str, description: str) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": name,
        "strict": True,
        "description": description,
        "schema": model.model_json_schema(),
    }


def response_output_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text

    parts: list[str] = []
    for item in getattr(response, "output", []):
        for content in getattr(item, "content", []):
            text = getattr(content, "text", None)
            if text:
                parts.append(text)
    return "\n".join(parts)


def response_output_parsed(response: Any) -> Any:
    output_parsed = getattr(response, "output_parsed", None)
    if output_parsed is not None:
        return output_parsed

    for item in getattr(response, "output", []):
        for content in getattr(item, "content", []):
            parsed = getattr(content, "parsed", None)
            if parsed is not None:
                return parsed
    return None


class EventAIService:
    def __init__(self, client: OpenAI, model: str = "gpt-5-mini") -> None:
        self._client = client
        self._model = model

    def parse_source_text(
        self,
        *,
        source_text: str,
        category: str,
        source_name: str,
        source_url: str,
        target_date: date,
        timezone: ZoneInfo,
    ) -> list[AIExtractedEvent]:
        prompt = f"""
Extract scheduled events from one source page.

Rules:
- Only include events happening on {target_date.isoformat()} in timezone {timezone.key}.
- Ignore events from other dates.
- Ignore vague mentions without a clear date.
- Prefer scheduled events.
- If a time is known, return ISO8601 datetime with timezone.
- If only the date is known, return YYYY-MM-DD.
- Use category "{category}" for every event.
- Use source "{source_name}" for every event.

Source URL: {source_url}
Visible text:
{source_text}
""".strip()

        try:
            if hasattr(self._client.responses, "parse"):
                response = self._client.responses.parse(
                    model=self._model,
                    reasoning={"effort": "low"},
                    input=prompt,
                    text_format=AIEventBatch,
                )
                parsed = response_output_parsed(response)
                LOGGER.info("AI parse response: %s", response_output_text(response)[:500])
                if parsed is not None:
                    return AIEventBatch.model_validate(parsed, from_attributes=True).events
                LOGGER.warning("AI parse returned no parsed payload for %s", source_url)
                return []

            response = self._client.responses.create(
                model=self._model,
                reasoning={"effort": "low"},
                input=prompt,
                text={"format": schema_payload(AIEventBatch, "daily_events", "Daily events for one source.")},
            )
            output_text = response_output_text(response)
            LOGGER.info("AI parse response: %s", output_text[:500])
            return AIEventBatch.model_validate_json(output_text).events
        except ValidationError as exc:
            LOGGER.warning("AI parse returned invalid structured output for %s: %s", source_url, exc)
            return []
        except Exception as exc:  # pragma: no cover - SDK exceptions vary by version
            LOGGER.warning("AI parse failed for %s: %s", source_url, exc)
            return []

    def discover_events(
        self,
        *,
        categories: Sequence[str],
        target_date: date,
        timezone: ZoneInfo,
    ) -> list[AIExtractedEvent]:
        category_list = ", ".join(categories)
        prompt = f"""
Find notable scheduled events happening on {target_date.isoformat()} in timezone {timezone.key}.

Rules:
- Only include events happening today in the provided timezone.
- Categories must be one of: {category_list}.
- Ignore vague mentions and events without a clear date.
- Prefer scheduled events.
- If a time is known, return ISO8601 datetime with timezone.
- If only the date is known, return YYYY-MM-DD.
- Keep source names short.
""".strip()

        tool = {
            "type": "web_search",
            "user_location": {
                "type": "approximate",
                "country": "US",
                "timezone": timezone.key,
            },
        }

        try:
            response = self._client.responses.create(
                model=self._model,
                reasoning={"effort": "low"},
                input=prompt,
                tools=[tool],
                text={"format": schema_payload(AIEventBatch, "discovered_events", "Discovered daily events.")},
            )
            output_text = response_output_text(response)
            LOGGER.info("AI discovery response: %s", output_text[:500])
            return AIEventBatch.model_validate_json(output_text).events
        except ValidationError as exc:
            LOGGER.warning("AI discovery returned invalid structured output: %s", exc)
            return []
        except Exception as exc:  # pragma: no cover - SDK exceptions vary by version
            LOGGER.warning("AI discovery failed: %s", exc)
            return []
