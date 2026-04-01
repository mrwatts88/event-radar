from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Iterable
from zoneinfo import ZoneInfo

from rapidfuzz import fuzz

from event_radar.ai import EventAIService
from event_radar.config import AppConfig
from event_radar.fetch import FetchError, extract_visible_text, fetch_html
from event_radar.models import AIExtractedEvent, EventRecord, EventTag


LOGGER = logging.getLogger(__name__)
TITLE_SIMILARITY_THRESHOLD = 90
TIME_WINDOW_MINUTES = 180


class EventRadarPipeline:
    def __init__(self, config: AppConfig, ai_service: EventAIService, session: object) -> None:
        self._config = config
        self._ai_service = ai_service
        self._session = session

    def run(self, target_date: date) -> list[EventRecord]:
        events: list[EventRecord] = []

        for category_name, category_config in self._config.categories.items():
            for source in category_config.sources:
                source_url = str(source.url)
                source_name = source.name or source_url
                LOGGER.info("Fetching URL: %s", source_url)
                try:
                    html = fetch_html(self._session, source_url, self._config.http.timeout_seconds)
                except FetchError as exc:
                    LOGGER.warning("Skipping source after fetch failure: %s", exc)
                    continue

                visible_text = extract_visible_text(html, self._config.http.max_chars)
                extracted_events = self._ai_service.parse_source_text(
                    source_text=visible_text,
                    category=category_name,
                    source_name=source_name,
                    source_url=source_url,
                    target_date=target_date,
                    timezone=self._config.zoneinfo,
                )
                events.extend(
                    normalize_events(
                        extracted_events,
                        target_date=target_date,
                        timezone=self._config.zoneinfo,
                        fallback_category=category_name,
                        fallback_source=source_name,
                        source_url=source_url,
                        tag=EventTag.CORE,
                    )
                )

        if self._config.discovery.enabled:
            discovered_events = self._ai_service.discover_events(
                categories=self._config.discovery.prompt_categories,
                target_date=target_date,
                timezone=self._config.zoneinfo,
            )
            events.extend(
                normalize_events(
                    discovered_events,
                    target_date=target_date,
                    timezone=self._config.zoneinfo,
                    fallback_category=None,
                    fallback_source=None,
                    source_url=None,
                    tag=EventTag.DISCOVERED,
                    allowed_categories=set(self._config.discovery.prompt_categories)
                    | set(self._config.categories.keys()),
                )
            )

        merged_events = deduplicate_events(events)
        filtered_events = apply_filters(merged_events, self._config)
        sorted_events = sort_events(filtered_events)
        LOGGER.info("Final event count: %s", len(sorted_events))
        return sorted_events


def normalize_events(
    extracted_events: Iterable[AIExtractedEvent],
    *,
    target_date: date,
    timezone: ZoneInfo,
    fallback_category: str | None,
    fallback_source: str | None,
    source_url: str | None,
    tag: EventTag,
    allowed_categories: set[str] | None = None,
) -> list[EventRecord]:
    normalized: list[EventRecord] = []
    for extracted_event in extracted_events:
        category = fallback_category or extracted_event.category.strip()
        source = fallback_source or extracted_event.source.strip()

        if not category or not source:
            continue
        if allowed_categories is not None and category not in allowed_categories:
            continue

        parsed = parse_event_datetime(extracted_event.datetime, timezone)
        if parsed is None:
            continue
        event_datetime, local_date, time_known = parsed
        if local_date != target_date:
            continue

        normalized.append(
            EventRecord(
                title=extracted_event.title.strip(),
                datetime=event_datetime,
                local_date=local_date,
                category=category,
                source=source,
                source_url=source_url,
                confidence=extracted_event.confidence,
                tag=tag,
                time_known=time_known,
            )
        )
    return normalized


def parse_event_datetime(raw_value: str | None, timezone: ZoneInfo) -> tuple[datetime | None, date, bool] | None:
    if raw_value is None:
        return None

    value = raw_value.strip()
    if not value:
        return None

    if "T" not in value and " " not in value:
        try:
            local_date = date.fromisoformat(value)
        except ValueError:
            return None
        return None, local_date, False

    try:
        parsed_datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed_datetime.tzinfo is None:
        parsed_datetime = parsed_datetime.replace(tzinfo=timezone)

    local_datetime = parsed_datetime.astimezone(timezone)
    return local_datetime, local_datetime.date(), True


def deduplicate_events(events: list[EventRecord]) -> list[EventRecord]:
    ordered_events = sorted(
        events,
        key=lambda event: (
            0 if event.tag == EventTag.CORE else 1,
            -event.confidence,
            0 if event.time_known else 1,
            event.title.lower(),
        ),
    )

    deduped: list[EventRecord] = []
    for event in ordered_events:
        if any(events_match(event, kept) for kept in deduped):
            continue
        deduped.append(event)
    return deduped


def events_match(left: EventRecord, right: EventRecord) -> bool:
    if left.category != right.category:
        return False

    left_title = normalize_title(left.title)
    right_title = normalize_title(right.title)
    title_score = fuzz.token_sort_ratio(left_title, right_title)
    titles_match = left_title == right_title or title_score >= TITLE_SIMILARITY_THRESHOLD
    if not titles_match:
        return False

    if left.local_date != right.local_date:
        return False

    if left.time_known and right.time_known and left.datetime and right.datetime:
        minutes_apart = abs((left.datetime - right.datetime).total_seconds()) / 60
        return minutes_apart <= TIME_WINDOW_MINUTES

    return True


def normalize_title(title: str) -> str:
    lowered = title.lower()
    alphanumeric = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", alphanumeric).strip()


def apply_filters(events: list[EventRecord], config: AppConfig) -> list[EventRecord]:
    filtered: list[EventRecord] = []
    for event in events:
        category_config = config.categories.get(event.category)
        min_confidence = config.filters.min_confidence
        include_keywords: list[str] = []

        if category_config is not None:
            if category_config.filters.min_confidence is not None:
                min_confidence = category_config.filters.min_confidence
            include_keywords = category_config.filters.include_keywords

        if event.confidence < min_confidence:
            continue

        if include_keywords:
            haystack = f"{event.title} {event.source}".lower()
            if not any(keyword.lower() in haystack for keyword in include_keywords):
                continue

        filtered.append(event)

    return filtered


def sort_events(events: list[EventRecord]) -> list[EventRecord]:
    return sorted(
        events,
        key=lambda event: (
            event.local_date,
            0 if event.time_known else 1,
            event.datetime or datetime.max.replace(tzinfo=ZoneInfo("UTC")),
            event.category,
            event.title.lower(),
        ),
    )
