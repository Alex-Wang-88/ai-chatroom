import asyncio
from collections.abc import AsyncIterator

import pytest
from app.config import Settings
from app.db.base import Base
from app.models import Agent
from app.orchestrator.service import ConversationOrchestrator
from app.providers import GenerationConfig, ProviderChunk, ProviderRegistry
from app.realtime.event_hub import ConversationEventHub
from app.schemas.commands import DebateResponseCreate
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


class RecordingProvider:
    def __init__(self) -> None:
        self.requests: list[tuple[str, list[object]]] = []

    async def stream_chat(
        self,
        messages: list[object],
        generation_config: GenerationConfig,
        cancellation_event: asyncio.Event,
    ) -> AsyncIterator[ProviderChunk]:
        self.requests.append((generation_config.model, messages))
        yield ProviderChunk(text="x" * 600)
        yield ProviderChunk(done=True)


@pytest.fixture
async def debate_harness():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    settings = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite://",
        jimo_authorization="test",
        jimo_share_url_deepseekv4lash="https://example.test/deepseek",
        jimo_share_url_qwen36flash="https://example.test/qwen",
        jimo_share_url_glm53flash="https://example.test/glm",
    )
    provider = RecordingProvider()
    registry = ProviderRegistry()
    registry.register("jimo", provider)
    service = ConversationOrchestrator(settings, sessions, registry, ConversationEventHub())
    await service.seed_agents()
    async with sessions() as session:
        agents = list((await session.execute(select(Agent).order_by(Agent.mention_handle))).scalars().all())
    yield service, sessions, provider, agents
    await engine.dispose()


def _request(**overrides: object) -> DebateResponseCreate:
    values: dict[str, object] = {
        "debate_id": "debate-1",
        "topic": "地球是不是圆的？",
        "pro_agent_id": "agent-pro",
        "con_agent_id": "agent-con",
        "side": "pro",
        "history": [],
    }
    values.update(overrides)
    return DebateResponseCreate.model_validate(values)


def test_debate_request_supports_topic_or_both_positions_and_enforces_order():
    assert _request().topic == "地球是不是圆的？"
    positions = _request(topic=None, pro_position="支持", con_position="反对")
    assert positions.pro_position == "支持"

    with pytest.raises(ValidationError):
        _request(topic=None, pro_position="支持")
    with pytest.raises(ValidationError):
        _request(pro_position="支持", con_position="反对")
    with pytest.raises(ValidationError):
        _request(side="con")


@pytest.mark.asyncio
async def test_debate_response_uses_selected_agent_without_limiting_output(debate_harness):
    service, _, provider, agents = debate_harness
    pro_agent, con_agent = agents[0], agents[1]
    content, selected = await service.generate_debate_response(
        debate_id="debate-1",
        topic="地球是不是圆的？",
        pro_position=None,
        con_position=None,
        pro_agent_id=pro_agent.id,
        con_agent_id=con_agent.id,
        side="pro",
        history=[],
    )

    assert selected.id == pro_agent.id
    assert len(content) == 600
    assert provider.requests[0][0] == pro_agent.model_id
    user_prompt = provider.requests[0][1][-1].content
    assert "地球是不是圆的？" in user_prompt
    assert "当前身份：正方" in user_prompt
    assert "开篇立论" in user_prompt


@pytest.mark.asyncio
async def test_debate_response_can_stream_deltas_and_finish_with_metadata(debate_harness):
    service, _, _, agents = debate_harness
    events = [
        event
        async for event in service.stream_debate_response(
            debate_id="debate-stream",
            topic="地球是不是圆的？",
            pro_position=None,
            con_position=None,
            pro_agent_id=agents[0].id,
            con_agent_id=agents[1].id,
            side="pro",
            history=[],
        )
    ]

    assert events[0]["event"] == "start"
    assert any(event["event"] == "delta" for event in events)
    assert events[-1]["event"] == "done"
    delta_text = "".join(event["text"] for event in events if event["event"] == "delta")
    assert len(delta_text) == 600
    assert len(events[-1]["content"]) == 600
    assert "truncated" not in events[-1]


@pytest.mark.asyncio
async def test_debate_history_persists_and_can_be_renamed(debate_harness):
    service, _, _, agents = debate_harness
    debate = await service.create_debate(
        title=None,
        topic="地球是不是圆的？",
        pro_position=None,
        con_position=None,
        pro_agent_id=agents[0].id,
        con_agent_id=agents[1].id,
    )

    content, selected = await service.generate_debate_response(
        debate_id=debate.id,
        topic=debate.topic,
        pro_position=debate.pro_position,
        con_position=debate.con_position,
        pro_agent_id=debate.pro_agent_id,
        con_agent_id=debate.con_agent_id,
        side="pro",
        history=[],
        persist=True,
    )

    stored = await service.get_debate(debate.id)
    assert stored is not None
    assert stored.title == "地球是不是圆的？"
    assert len(stored.turns) == 1
    assert stored.turns[0].content == content
    assert stored.turns[0].agent_id == selected.id

    stream_events = [
        event
        async for event in service.stream_debate_response(
            debate_id=debate.id,
            topic=debate.topic,
            pro_position=debate.pro_position,
            con_position=debate.con_position,
            pro_agent_id=debate.pro_agent_id,
            con_agent_id=debate.con_agent_id,
            side="con",
            history=[{"side": "pro", "content": content}],
            persist=True,
        )
    ]
    assert stream_events[-1]["event"] == "done"
    stored = await service.get_debate(debate.id)
    assert stored is not None
    assert [turn.side for turn in stored.turns] == ["pro", "con"]

    renamed = await service.rename_debate(debate.id, "地球形状讨论")
    assert renamed.title == "地球形状讨论"
    ended = await service.end_debate(debate.id)
    assert ended.status == "ended"
