import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import Settings
from app.providers.base import ChatMessage, GenerationConfig, ProviderError
from app.providers.events import ProviderChunk

logger = logging.getLogger(__name__)


class SSEProtocolError(ProviderError):
    def __init__(self, message: str):
        super().__init__(message, "malformed_sse")


def _extract_chunk(payload: dict[str, Any]) -> ProviderChunk:
    if payload.get("error"):
        detail = payload["error"]
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("code") or "Jimo provider returned an error"
        raise ProviderError(str(detail)[:500], "provider_error")
    # Jimo share agents multiplex workflow/reasoning events with the answer
    # stream.  ``type=thinking`` (and its aliases) is internal model output,
    # not text that should be persisted or shown to the user.  Workflow
    # events generally do not have a ``content`` field and are ignored by
    # the normal extraction below; keeping this filter here also protects us
    # if a provider includes a short status string in that field.
    payload_type = str(payload.get("type") or "").strip().lower()
    hidden_types = {"thinking", "reasoning", "analysis", "thought", "workflow", "tool", "event"}
    text = "" if payload_type in hidden_types else payload.get("content")
    finish_reason = payload.get("finish_reason")
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0] or {}
        delta = choice.get("delta") or {}
        # OpenAI-compatible deltas are always user-visible answer content;
        # the type filter above only applies to Jimo's custom payload shape.
        text = delta.get("content") or choice.get("text") or text
        finish_reason = choice.get("finish_reason") or finish_reason

    usage = payload.get("usage") or {}
    done = bool(payload.get("done") is True or payload.get("end") is not None)
    if finish_reason is not None:
        done = True
    return ProviderChunk(
        text=str(text) if text else "",
        done=done,
        finish_reason=str(finish_reason) if finish_reason else None,
        input_tokens=usage.get("prompt_tokens") or usage.get("input_tokens"),
        output_tokens=usage.get("completion_tokens") or usage.get("output_tokens"),
        provider_request_id=payload.get("id") or payload.get("request_id"),
        raw=payload,
    )


async def parse_sse_lines(lines: AsyncIterator[str]) -> AsyncIterator[ProviderChunk]:
    event_name = "message"
    data_lines: list[str] = []

    async def flush() -> AsyncIterator[ProviderChunk]:
        nonlocal event_name, data_lines
        if event_name == "end":
            yield ProviderChunk(done=True)
            event_name, data_lines = "message", []
            return
        if not data_lines:
            event_name, data_lines = "message", []
            return
        data = "\n".join(data_lines).strip()
        event_name, data_lines = "message", []
        if data in {"[DONE]", "DONE"}:
            yield ProviderChunk(done=True)
            return
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as exc:
            raise SSEProtocolError("SSE data was not valid JSON") from exc
        if not isinstance(payload, dict):
            raise SSEProtocolError("SSE data must be a JSON object")
        yield _extract_chunk(payload)

    async for raw_line in lines:
        line = raw_line.rstrip("\r")
        if line == "":
            async for chunk in flush():
                yield chunk
                if chunk.done:
                    return
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if not separator:
            continue
        value = value.removeprefix(" ")
        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)

    async for chunk in flush():
        yield chunk


class JimoProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    def _headers(self, auth_scheme: str | None = None) -> dict[str, str]:
        token = self.settings.jimo_authorization.strip()
        if not token:
            raise ProviderError("Jimo authorization is not configured", "configuration_error")
        scheme = (auth_scheme or self.settings.jimo_auth_scheme).lower()
        if scheme == "bearer" and not token.lower().startswith("bearer "):
            token = f"Bearer {token}"
        return {"Authorization": token, "Accept": "text/event-stream", "Content-Type": "application/json"}

    def _url(self, endpoint: str | None = None) -> str:
        target = endpoint or self.settings.jimo_chat_endpoint
        if target.startswith(("http://", "https://")):
            return target
        return f"{self.settings.jimo_base_url.rstrip('/')}/{target.lstrip('/')}"

    def _redact(self, text: str) -> str:
        token = self.settings.jimo_authorization.strip()
        if token:
            text = text.replace(token, "[REDACTED]")
            text = text.replace(f"Bearer {token}", "Bearer [REDACTED]")
        return text

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        generation_config: GenerationConfig,
        cancellation_event: asyncio.Event,
    ) -> AsyncIterator[ProviderChunk]:
        timeout = httpx.Timeout(
            self.settings.jimo_timeout_seconds,
            connect=self.settings.jimo_connect_timeout_seconds,
            read=self.settings.jimo_idle_timeout_seconds,
        )
        endpoint = generation_config.extra.get("endpoint")
        auth_scheme = generation_config.extra.get("auth_scheme")
        body: dict[str, Any] = {
            "messages": [{"role": item.role, "content": item.content} for item in messages],
            "stream": generation_config.stream,
        }
        # OpenAI-compatible endpoints require a model, while a Jimo share
        # endpoint can resolve the agent from its shareId URL. Do not send an
        # empty model value to the latter.
        if generation_config.model:
            body["model"] = generation_config.model
        if endpoint and "/v2/chat/completions/share" in str(endpoint):
            body["sessionId"] = generation_config.extra.get("session_id")
            body["source"] = "api"
            body["extra"] = {}
        if generation_config.temperature is not None:
            body["temperature"] = generation_config.temperature
        if generation_config.max_output_tokens is not None:
            body["max_tokens"] = generation_config.max_output_tokens
        internal_keys = {"endpoint", "auth_scheme", "session_id"}
        body.update({key: value for key, value in generation_config.extra.items() if key not in internal_keys})
        client = self._client or httpx.AsyncClient(timeout=timeout)
        close_client = self._client is None
        try:
            async with client.stream("POST", self._url(str(endpoint) if endpoint else None), headers=self._headers(str(auth_scheme) if auth_scheme else None), json=body) as response:
                if response.status_code >= 400:
                    detail = self._redact((await response.aread())[:500].decode("utf-8", errors="replace"))
                    raise ProviderError(
                        f"Jimo request failed with HTTP {response.status_code}: {detail}",
                        "http_error",
                        status_code=response.status_code,
                    )
                async for chunk in parse_sse_lines(response.aiter_lines()):
                    if cancellation_event.is_set():
                        return
                    yield chunk
                    if chunk.done:
                        return
        except asyncio.CancelledError:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderError("Jimo request timed out", "timeout") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Jimo connection failed", "connection_error") from exc
        finally:
            if close_client:
                await client.aclose()
