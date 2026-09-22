import asyncio

import pytest
from app.providers.base import ProviderError
from app.providers.jimo import SSEProtocolError, parse_sse_lines


async def source(lines: list[str]):
    for line in lines:
        await asyncio.sleep(0)
        yield line


@pytest.mark.asyncio
async def test_custom_and_openai_sse_are_normalized():
    chunks = [chunk async for chunk in parse_sse_lines(source([
        "event: data", 'data: {"content":"你好"}', "", "data: {\"choices\":[{\"delta\":{\"content\":\"世界\"}}]}", "", "data: [DONE]", "",
    ]))]
    assert [chunk.text for chunk in chunks[:2]] == ["你好", "世界"]
    assert chunks[-1].done is True


@pytest.mark.asyncio
async def test_end_event_is_a_terminal_chunk():
    chunks = [chunk async for chunk in parse_sse_lines(source(["event: end", "data: {}", ""]))]
    assert len(chunks) == 1 and chunks[0].done


@pytest.mark.asyncio
async def test_malformed_json_is_explicit_error():
    with pytest.raises(SSEProtocolError):
        [chunk async for chunk in parse_sse_lines(source(["data: not-json", ""]))]


@pytest.mark.asyncio
async def test_provider_error_event_is_not_saved_as_empty_success():
    with pytest.raises(ProviderError, match="bad model"):
        [chunk async for chunk in parse_sse_lines(source(['data: {"error": {"message": "bad model"}}', ""]))]


@pytest.mark.asyncio
async def test_jimo_thinking_and_workflow_events_are_not_user_visible():
    chunks = [chunk async for chunk in parse_sse_lines(source([
        'event: event', 'data: {"text":"正在分析","status":"running"}', "",
        'event: data', 'data: {"type":"thinking","role":"assistant","content":"internal reasoning"}', "",
        'event: data', 'data: {"type":"data","role":"assistant","content":"可见答案"}', "",
        'event: end', 'data: {"end":true}', "",
    ]))]
    assert [chunk.text for chunk in chunks] == ["", "", "可见答案", ""]
    assert chunks[-1].done is True
