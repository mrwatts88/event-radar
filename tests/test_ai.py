from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from event_radar.ai import EventAIService
from event_radar.models import AIEventBatch


class FakeResponses:
    def __init__(self):
        self.parse_calls = []
        self.create_calls = []
        self.parse_response = SimpleNamespace(
            output_parsed=AIEventBatch.model_validate(
                {
                    "events": [
                        {
                            "title": "Bucks vs Heat",
                            "datetime": "2026-04-01T19:00:00-05:00",
                            "category": "sports",
                            "source": "ESPN Bucks Schedule",
                            "confidence": 0.9,
                        }
                    ]
                }
            ),
            output_text='{"events":[{"title":"Bucks vs Heat"}]}',
        )
        self.create_response = SimpleNamespace(
            output_text="""
{"events":[{"title":"SpaceX Launch","datetime":"2026-04-01T21:12:00-05:00","category":"space","source":"SpaceX","confidence":0.8}]}
""".strip()
        )

    def parse(self, **kwargs):
        self.parse_calls.append(kwargs)
        return self.parse_response

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return self.create_response


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


def test_parse_source_text_sends_expected_context():
    service = EventAIService(FakeClient())
    events = service.parse_source_text(
        source_text="Bucks at Heat on April 1 at 7 PM.",
        category="sports",
        source_name="ESPN Bucks Schedule",
        source_url="https://example.com/sports",
        target_date=date(2026, 4, 1),
        timezone=ZoneInfo("America/Chicago"),
    )

    assert len(events) == 1
    parse_call = service._client.responses.parse_calls[0]
    assert parse_call["model"] == "gpt-5-mini"
    assert "America/Chicago" in parse_call["input"]
    assert "https://example.com/sports" in parse_call["input"]
    assert "sports" in parse_call["input"]


def test_discovery_uses_web_search_and_parses_output():
    service = EventAIService(FakeClient())
    events = service.discover_events(
        categories=["space", "poker"],
        target_date=date(2026, 4, 1),
        timezone=ZoneInfo("America/Chicago"),
    )

    assert len(events) == 1
    create_call = service._client.responses.create_calls[0]
    assert create_call["tools"][0]["type"] == "web_search"
    assert create_call["tools"][0]["user_location"]["timezone"] == "America/Chicago"
    assert "space, poker" in create_call["input"]


def test_invalid_structured_output_returns_empty_list():
    client = FakeClient()
    client.responses.create_response = SimpleNamespace(output_text='{"events":[{"title":"SpaceX Launch","confidence":2.0}]}')
    service = EventAIService(client)

    events = service.discover_events(
        categories=["space"],
        target_date=date(2026, 4, 1),
        timezone=ZoneInfo("America/Chicago"),
    )

    assert events == []


def test_structured_output_schema_marks_nullable_datetime_as_required():
    schema = AIEventBatch.model_json_schema()
    event_schema = schema["$defs"]["AIExtractedEvent"]

    assert "datetime" in event_schema["required"]
    assert "events" in schema["required"]


def test_parse_failure_is_non_fatal():
    client = FakeClient()

    def broken_parse(**kwargs):
        raise RuntimeError("parse failed")

    client.responses.parse = broken_parse
    service = EventAIService(client)

    events = service.parse_source_text(
        source_text="ignored",
        category="sports",
        source_name="Source",
        source_url="https://example.com",
        target_date=date(2026, 4, 1),
        timezone=ZoneInfo("America/Chicago"),
    )

    assert events == []
