from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, field_validator, model_validator


SMTP_PASSWORD_ENV = "EVENT_RADAR_SMTP_PASSWORD"
ENV_VAR_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


class ConfigError(RuntimeError):
    """Raised when config or secret resolution fails."""


def default_timezone_name() -> str:
    env_timezone = os.environ.get("TZ")
    if env_timezone:
        return env_timezone

    local_tz = datetime.now().astimezone().tzinfo
    tz_key = getattr(local_tz, "key", None)
    if tz_key:
        return tz_key

    return "UTC"


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    name: str | None = None


class CategoryFilterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_keywords: list[str] = Field(default_factory=list)
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class CategoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[SourceConfig]
    filters: CategoryFilterConfig = Field(default_factory=CategoryFilterConfig)
    emoji: str | None = None


class HttpConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int = Field(default=10, ge=1, le=60)
    max_chars: int = Field(default=15000, ge=1000, le=50000)


class GlobalFilterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)


class DiscoveryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    prompt_categories: list[str] = Field(default_factory=list)


class SMTPConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    host: str
    port: int = Field(ge=1, le=65535)
    username: str
    from_address: str = Field(alias="from")
    to: list[str] = Field(min_length=1)


class DeliveryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str = "email"
    smtp: SMTPConfig

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        if value != "email":
            raise ValueError("delivery.method must be 'email' in v1")
        return value


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str = Field(default_factory=default_timezone_name)
    http: HttpConfig = Field(default_factory=HttpConfig)
    filters: GlobalFilterConfig = Field(default_factory=GlobalFilterConfig)
    categories: dict[str, CategoryConfig]
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    delivery: DeliveryConfig

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"invalid timezone: {value}") from exc
        return value

    @model_validator(mode="after")
    def populate_discovery_categories(self) -> "AppConfig":
        if not self.categories:
            raise ValueError("at least one category is required")
        if not self.discovery.prompt_categories:
            self.discovery.prompt_categories = list(self.categories.keys())
        return self

    @property
    def zoneinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@dataclass(slots=True)
class RuntimeSecrets:
    openai_api_key: str
    smtp_password: str | None


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise ConfigError(f"config file not found: {config_path}")

    suffix = config_path.suffix.lower()
    raw_text = config_path.read_text(encoding="utf-8")
    if suffix == ".json":
        raw_data = json.loads(raw_text)
    elif suffix in {".yaml", ".yml"}:
        raw_data = yaml.safe_load(raw_text)
    else:
        raise ConfigError("config file must be .json, .yaml, or .yml")

    if not isinstance(raw_data, dict):
        raise ConfigError("config root must be an object")

    expanded_data = expand_env_placeholders(raw_data)

    try:
        return AppConfig.model_validate(expanded_data)
    except ValidationError as exc:
        raise ConfigError(str(exc)) from exc


def expand_env_placeholders(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: expand_env_placeholders(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env_placeholders(item) for item in value]
    if isinstance(value, str):
        return ENV_VAR_PATTERN.sub(replace_env_match, value)
    return value


def replace_env_match(match: re.Match[str]) -> str:
    env_var = match.group(1)
    value = os.environ.get(env_var)
    if value is None:
        raise ConfigError(f"missing environment variable for config placeholder: {env_var}")
    return value


def resolve_secrets(
    env: Mapping[str, str] | None = None,
    *,
    require_smtp_password: bool = True,
) -> RuntimeSecrets:
    source = env or os.environ
    openai_api_key = source.get("OPENAI_API_KEY", "").strip()
    if not openai_api_key:
        raise ConfigError("missing OPENAI_API_KEY")

    smtp_password = source.get(SMTP_PASSWORD_ENV, "").strip() or None
    if require_smtp_password and not smtp_password:
        raise ConfigError(f"missing {SMTP_PASSWORD_ENV}")

    return RuntimeSecrets(openai_api_key=openai_api_key, smtp_password=smtp_password)
