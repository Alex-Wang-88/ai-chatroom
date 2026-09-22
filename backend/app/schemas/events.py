from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    protocol_version: int = 1
    type: str
    stream_epoch: str
    sequence: int
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    conversation_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


def event_payload(event_type: str, conversation_id: str, payload: dict[str, Any], epoch: str, sequence: int) -> dict[str, Any]:
    return EventEnvelope(
        type=event_type,
        stream_epoch=epoch or str(uuid4()),
        sequence=sequence,
        conversation_id=conversation_id,
        payload=payload,
    ).model_dump(mode="json")
