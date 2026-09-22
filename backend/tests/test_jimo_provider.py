import asyncio
import json

import httpx
import pytest
from app.config import Settings
from app.providers import ChatMessage, GenerationConfig, JimoProvider


@pytest.mark.asyncio
async def test_share_endpoint_uses_raw_auth_and_session_metadata() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = json.loads(request.content)
        stream = b"event: data\ndata: {\"content\":\"ok\"}\n\nevent: end\ndata: {}\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=stream)

    settings = Settings(
        _env_file=None,
        jimo_authorization="raw-secret",
        jimo_auth_scheme="bearer",
        jimo_base_url="https://example.test",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = JimoProvider(settings, client)
        chunks = [
            chunk
            async for chunk in provider.stream_chat(
                [ChatMessage(role="user", content="hello")],
                GenerationConfig(
                    model="",
                    extra={
                        "endpoint": "https://example.test/v2/chat/completions/share?shareId=demo",
                        "auth_scheme": "raw",
                        "session_id": "conversation-1",
                    },
                ),
                asyncio.Event(),
            )
        ]

    assert captured["url"].endswith("shareId=demo")
    assert captured["authorization"] == "raw-secret"
    assert captured["body"]["sessionId"] == "conversation-1"
    assert captured["body"]["source"] == "api"
    assert "endpoint" not in captured["body"]
    assert "auth_scheme" not in captured["body"]
    assert "session_id" not in captured["body"]
    assert "model" not in captured["body"]
    assert [chunk.text for chunk in chunks if chunk.text] == ["ok"]
    assert chunks[-1].done is True
