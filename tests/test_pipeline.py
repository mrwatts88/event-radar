from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from event_radar.config import AppConfig
from event_radar.models import EventRecord, EventTag
from event_radar.models import AIExtractedEvent
from event_radar.pipeline import apply_filters, deduplicate_events, normalize_events, sort_events


def build_config() -> AppConfig:
    return AppConfig.model_validate(
        {
            "timezone": "America/Chicago",
            "filters": {"min_confidence": 0.6},
            "categories": {
                "sports": {
                    "emoji": "🏀",
                    "sources": [{"url": "https://example.com/sports"}],
                    "filters": {"include_keywords": ["Bucks"]},
                },
                "space": {
                    "emoji": "🚀",
                    "sources": [{"url": "https://example.com/space"}],
                },
            },
            "delivery": {
                "method": "email",
                "smtp": {
                    "host": "smtp.example.com",
                    "port": 587,
                    "username": "user@example.com",
                    "from": "sender@example.com",
                    "to": ["you@example.com"],
                },
            },
        }
    )


def test_core_event_beats_discovered_duplicate():
    tz = ZoneInfo("America/Chicago")
    core_event = EventRecord(
        title="Bucks vs Heat",
        datetime=datetime(2026, 4, 1, 19, 0, tzinfo=tz),
        local_date=date(2026, 4, 1),
        category="sports",
        source="ESPN",
        source_url="https://example.com",
        confidence=0.8,
        tag=EventTag.CORE,
        time_known=True,
    )
    discovered_event = EventRecord(
        title="Bucks vs. Heat",
        datetime=datetime(2026, 4, 1, 18, 45, tzinfo=tz),
        local_date=date(2026, 4, 1),
        category="sports",
        source="Web",
        source_url=None,
        confidence=0.95,
        tag=EventTag.DISCOVERED,
        time_known=True,
    )

    deduped = deduplicate_events([discovered_event, core_event])

    assert deduped == [core_event]


def test_filters_apply_keywords_and_confidence_thresholds():
    config = build_config()
    tz = ZoneInfo("America/Chicago")
    good_event = EventRecord(
        title="Bucks vs Heat",
        datetime=datetime(2026, 4, 1, 19, 0, tzinfo=tz),
        local_date=date(2026, 4, 1),
        category="sports",
        source="ESPN",
        source_url="https://example.com",
        confidence=0.9,
        tag=EventTag.CORE,
        time_known=True,
    )
    keyword_miss = EventRecord(
        title="Heat vs Bulls",
        datetime=datetime(2026, 4, 1, 19, 0, tzinfo=tz),
        local_date=date(2026, 4, 1),
        category="sports",
        source="ESPN",
        source_url="https://example.com",
        confidence=0.9,
        tag=EventTag.CORE,
        time_known=True,
    )
    low_confidence = EventRecord(
        title="SpaceX Launch",
        datetime=datetime(2026, 4, 1, 21, 12, tzinfo=tz),
        local_date=date(2026, 4, 1),
        category="space",
        source="SpaceX",
        source_url="https://example.com",
        confidence=0.4,
        tag=EventTag.DISCOVERED,
        time_known=True,
    )

    filtered = apply_filters([good_event, keyword_miss, low_confidence], config)

    assert filtered == [good_event]


def test_sort_puts_date_only_events_after_timed_events():
    tz = ZoneInfo("America/Chicago")
    date_only = EventRecord(
        title="WSOP Event #12 Day 2",
        datetime=None,
        local_date=date(2026, 4, 1),
        category="poker",
        source="WSOP",
        source_url=None,
        confidence=0.8,
        tag=EventTag.DISCOVERED,
        time_known=False,
    )
    timed = EventRecord(
        title="Bucks vs Heat",
        datetime=datetime(2026, 4, 1, 19, 0, tzinfo=tz),
        local_date=date(2026, 4, 1),
        category="sports",
        source="ESPN",
        source_url="https://example.com",
        confidence=0.9,
        tag=EventTag.CORE,
        time_known=True,
    )

    assert sort_events([date_only, timed]) == [timed, date_only]


def test_normalize_events_expands_schedule_shorthand_titles_from_source_name():
    normalized = normalize_events(
        [
            AIExtractedEvent(
                title="@ Golden State",
                datetime="2026-04-01T22:00:00-05:00",
                category="sports",
                source="ESPN Spurs Schedule",
                confidence=0.8,
            ),
            AIExtractedEvent(
                title="vs Tampa Bay Rays",
                datetime="2026-04-01",
                category="sports",
                source="ESPN Brewers Schedule",
                confidence=0.8,
            ),
        ],
        target_date=date(2026, 4, 1),
        timezone=ZoneInfo("America/Chicago"),
        fallback_category="sports",
        fallback_source=None,
        source_url="https://example.com",
        tag=EventTag.CORE,
    )

    assert normalized[0].title == "San Antonio Spurs at Golden State"
    assert normalized[1].title == "Milwaukee Brewers vs Tampa Bay Rays"
