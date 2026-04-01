from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EventTag(StrEnum):
    CORE = "core"
    DISCOVERED = "discovered"


@dataclass(slots=True)
class EventRecord:
    title: str
    datetime: datetime | None
    local_date: date
    category: str
    source: str
    source_url: str | None
    confidence: float
    tag: EventTag
    time_known: bool


class AIExtractedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    title: str
    datetime: str | None
    category: str
    source: str
    confidence: float = Field(ge=0.0, le=1.0)


class AIEventBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    events: list[AIExtractedEvent]
