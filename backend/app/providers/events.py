from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ProviderChunk:
    text: str = ""
    done: bool = False
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_request_id: str | None = None
    raw: dict[str, Any] | None = None
