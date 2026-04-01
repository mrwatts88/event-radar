from __future__ import annotations

import json

import pytest

from event_radar.config import ConfigError, SMTP_PASSWORD_ENV, load_config, resolve_secrets


def test_loads_yaml_and_json_configs(tmp_path):
    yaml_config = tmp_path / "config.yaml"
    yaml_config.write_text(
        """
timezone: America/Chicago
categories:
  sports:
    sources:
      - url: https://example.com/sports
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

    json_config = tmp_path / "config.json"
    json_config.write_text(
        json.dumps(
            {
                "timezone": "America/Chicago",
                "categories": {"sports": {"sources": [{"url": "https://example.com/sports"}]}},
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
        ),
        encoding="utf-8",
    )

    yaml_loaded = load_config(yaml_config)
    json_loaded = load_config(json_config)

    assert yaml_loaded.timezone == "America/Chicago"
    assert json_loaded.categories["sports"].sources[0].name is None
    assert yaml_loaded.discovery.prompt_categories == ["sports"]


def test_invalid_timezone_raises_config_error(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
timezone: Mars/Olympus
categories:
  sports:
    sources:
      - url: https://example.com/sports
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

    with pytest.raises(ConfigError):
        load_config(config_path)


def test_secret_resolution_injects_from_env():
    secrets = resolve_secrets(
        {
            "OPENAI_API_KEY": "test-openai-key",
            SMTP_PASSWORD_ENV: "test-smtp-password",
        }
    )
    assert secrets.openai_api_key == "test-openai-key"
    assert secrets.smtp_password == "test-smtp-password"


def test_missing_smtp_secret_raises():
    with pytest.raises(ConfigError):
        resolve_secrets({"OPENAI_API_KEY": "test-openai-key"})


def test_load_config_expands_env_placeholders(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
timezone: America/Chicago
categories:
  sports:
    sources:
      - url: https://example.com/sports
delivery:
  method: email
  smtp:
    host: smtp.gmail.com
    port: 587
    username: ${SMTP_USERNAME}
    from: ${SMTP_FROM}
    to:
      - ${SMTP_TO}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("SMTP_USERNAME", "user@example.com")
    monkeypatch.setenv("SMTP_FROM", "sender@example.com")
    monkeypatch.setenv("SMTP_TO", "to@example.com")

    config = load_config(config_path)

    assert config.delivery.smtp.username == "user@example.com"
    assert config.delivery.smtp.from_address == "sender@example.com"
    assert config.delivery.smtp.to == ["to@example.com"]
