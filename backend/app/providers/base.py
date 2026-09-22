import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.providers.events import ProviderChunk


@dataclass(slots=True, frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(slots=True, frozen=True)
class GenerationConfig:
    model: str
    temperature: float | None = None
    max_output_tokens: int | None = None
    stream: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


class ProviderError(RuntimeError):
    def __init__(self, message: str, error_type: str = "provider_error", *, status_code: int | None = None):
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code


class Provider(Protocol):
    async def stream_chat(
        self,
        messages: list[ChatMessage],
        generation_config: GenerationConfig,
        cancellation_event: asyncio.Event,
    ) -> AsyncIterator[ProviderChunk]: ...
