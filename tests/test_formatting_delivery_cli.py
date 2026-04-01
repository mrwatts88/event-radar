from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from event_radar.cli import main
from event_radar.config import AppConfig
from event_radar.delivery import send_email
from event_radar.formatting import build_email_subject, format_daily_summary
from event_radar.models import EventRecord, EventTag


def build_config() -> AppConfig:
    return AppConfig.model_validate(
        {
            "timezone": "America/Chicago",
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


def test_formatting_includes_sections_and_time():
    config = build_config()
    event = EventRecord(
        title="Bucks vs Heat",
        datetime=datetime(2026, 4, 1, 19, 0, tzinfo=ZoneInfo("America/Chicago")),
        local_date=date(2026, 4, 1),
        category="sports",
        source="ESPN",
        source_url="https://example.com",
        confidence=0.9,
        tag=EventTag.CORE,
        time_known=True,
    )

    body = format_daily_summary([event], config, date(2026, 4, 1))

    assert "TODAY - 2026-04-01" in body
    assert "CORE" in body
    assert "🏀 Bucks vs Heat - 7:00 PM" in body
    assert build_email_subject(date(2026, 4, 1)) == "Today's Events - 2026-04-01"


def test_formatting_handles_no_events():
    config = build_config()
    body = format_daily_summary([], config, date(2026, 4, 1))
    assert body == "TODAY - 2026-04-01\n\nNo relevant events found."


def test_send_email_uses_smtp(monkeypatch):
    config = build_config()
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            sent["tls"] = True

        def login(self, username, password):
            sent["username"] = username
            sent["password"] = password

        def send_message(self, message):
            sent["subject"] = message["Subject"]
            sent["to"] = message["To"]

    monkeypatch.setattr("event_radar.delivery.smtplib.SMTP", FakeSMTP)
    send_email(config, "Today's Events - 2026-04-01", "Body", "smtp-password")

    assert sent["host"] == "smtp.example.com"
    assert sent["tls"] is True
    assert sent["password"] == "smtp-password"
    assert sent["subject"] == "Today's Events - 2026-04-01"


def test_cli_run_end_to_end_with_mocked_http_openai_and_smtp(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
timezone: America/Chicago
categories:
  sports:
    emoji: "🏀"
    sources:
      - url: https://example.com/sports
        name: ESPN Bucks Schedule
    filters:
      include_keywords: ["Bucks"]
discovery:
  enabled: true
delivery:
  method: email
  smtp:
    host: smtp.example.com
    port: 587
    username: user@example.com
    from: sender@example.com
    to:
      - you@example.com
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("EVENT_RADAR_SMTP_PASSWORD", "smtp-password")

    class FakeSession:
        def get(self, url, timeout):
            return SimpleNamespace(
                text="<html><body><p>Bucks vs Heat on April 1 at 7:00 PM</p></body></html>",
                raise_for_status=lambda: None,
            )

    class FakeResponses:
        def parse(self, **kwargs):
            return SimpleNamespace(
                output_parsed=SimpleNamespace(
                    events=[
                        SimpleNamespace(
                            title="Bucks vs Heat",
                            datetime="2026-04-01T19:00:00-05:00",
                            category="sports",
                            source="ESPN Bucks Schedule",
                            confidence=0.9,
                        )
                    ]
                ),
                output_text='{"events":[{"title":"Bucks vs Heat"}]}',
            )

        def create(self, **kwargs):
            return SimpleNamespace(output_text='{"events":[]}')

    class FakeClient:
        def __init__(self):
            self.responses = FakeResponses()

    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            sent["tls"] = True

        def login(self, username, password):
            sent["username"] = username
            sent["password"] = password

        def send_message(self, message):
            sent["body"] = message.get_content()
            sent["subject"] = message["Subject"]

    monkeypatch.setattr("event_radar.cli.create_session", lambda: FakeSession())
    monkeypatch.setattr("event_radar.cli.build_openai_client", lambda api_key: FakeClient())
    monkeypatch.setattr("event_radar.delivery.smtplib.SMTP", FakeSMTP)

    exit_code = main(["run", "--config", str(config_path), "--date", "2026-04-01"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == ""
    assert sent["subject"] == "Today's Events - 2026-04-01"
    assert "Bucks vs Heat - 7:00 PM" in sent["body"]
