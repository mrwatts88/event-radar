from __future__ import annotations

from datetime import date

from event_radar.config import AppConfig
from event_radar.models import EventRecord, EventTag


def build_email_subject(target_date: date) -> str:
    return f"Today's Events - {target_date.isoformat()}"


def format_daily_summary(events: list[EventRecord], config: AppConfig, target_date: date) -> str:
    lines = [f"TODAY - {target_date.isoformat()}"]
    if not events:
        lines.extend(["", "No relevant events found."])
        return "\n".join(lines)

    core_events = [event for event in events if event.tag == EventTag.CORE]
    discovered_events = [event for event in events if event.tag == EventTag.DISCOVERED]

    if core_events:
        lines.extend(["", "CORE"])
        lines.extend(_format_event_line(event, config) for event in core_events)

    if discovered_events:
        lines.extend(["", "DISCOVERED"])
        lines.extend(_format_event_line(event, config) for event in discovered_events)

    return "\n".join(lines)


def _format_event_line(event: EventRecord, config: AppConfig) -> str:
    category = config.categories.get(event.category)
    prefix = f"{category.emoji} " if category and category.emoji else ""
    if event.time_known and event.datetime is not None:
        time_text = event.datetime.astimezone(config.zoneinfo).strftime("%I:%M %p").lstrip("0")
        return f"{prefix}{event.title} - {time_text}"
    return f"{prefix}{event.title}"
