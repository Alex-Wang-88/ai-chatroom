import asyncio
from collections.abc import AsyncIterator

import pytest
from app.config import Settings
from app.db.base import Base
from app.models import Agent, GenerationRun, Message, Round
from app.orchestrator.service import ConversationOrchestrator, _jimo_session_id
from app.providers import GenerationConfig, ProviderChunk, ProviderRegistry
from app.realtime.event_hub import ConversationEventHub
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


class FakeProvider:
    def __init__(self, outputs: dict[str, list[str]] | None = None):
        self.outputs = outputs or {}
        self.started: list[str] = []
        self.requests: list[tuple[str, dict]] = []

    async def stream_chat(self, messages, generation_config: GenerationConfig, cancellation_event: asyncio.Event) -> AsyncIterator[ProviderChunk]:
        self.started.append(generation_config.model)
        self.requests.append((generation_config.model, dict(generation_config.extra)))
        for text in self.outputs.get(generation_config.model, [generation_config.model]):
            await asyncio.sleep(0)
            if cancellation_event.is_set():
                return
            yield ProviderChunk(text=text)
        yield ProviderChunk(done=True)


@pytest.fixture
async def harness(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    settings = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite://",
        jimo_authorization="test",
        context_character_budget=1000,
        jimo_share_url_deepseekv4lash="https://example.test/deepseek",
        jimo_share_url_qwen36flash="https://example.test/qwen",
        jimo_share_url_glm53flash="https://example.test/glm",
    )
    provider = FakeProvider({"deep": ["D1", "D2"], "qwen": ["Q1", "Q2"], "glm": ["G1", "G2"]})
    registry = ProviderRegistry()
    registry.register("jimo", provider)
    service = ConversationOrchestrator(settings, sessions, registry, ConversationEventHub())
    await service.seed_agents()
    # Use confirmed-looking IDs only inside the fake provider; no network is called.
    async with sessions() as session:
        agents = list((await session.execute(__import__('sqlalchemy').select(Agent).order_by(Agent.mention_handle))).scalars().all())
        for agent, model in zip(agents, ["deep", "qwen", "glm"], strict=True):
            agent.model_id = model
        await session.commit()
    conversation = await service.create_conversation()
    yield service, sessions, provider, conversation
    await engine.dispose()


@pytest.mark.asyncio
async def test_topic_runs_parallel_and_persists_messages(harness):
    service, sessions, provider, conversation = harness
    _, round_row = await service.submit_message(conversation.id, "大家怎么看？", "client-1")
    await service._conversation_tasks[conversation.id]
    assert set(provider.started) == {"deep", "qwen", "glm"}
    async with sessions() as session:
        messages = list((await session.execute(__import__('sqlalchemy').select(Message).where(Message.conversation_id == conversation.id))).scalars().all())
        runs = list((await session.execute(__import__('sqlalchemy').select(GenerationRun).where(GenerationRun.round_id == round_row.id))).scalars().all())
    agent_messages = [message for message in messages if message.sender_type == "agent"]
    assert all(message.status == "completed" for message in agent_messages)
    assert [message.display_sequence for message in sorted(agent_messages, key=lambda item: item.display_sequence or 0)] == [2, 3, 4]
    assert all(run.status == "completed" for run in runs)
    sessions_by_model = {model: extra["session_id"] for model, extra in provider.requests}
    assert len(sessions_by_model) == 3
    assert len(set(sessions_by_model.values())) == 3


@pytest.mark.asyncio
async def test_idempotent_message_submission_returns_same_round(harness):
    service, _, _, conversation = harness
    first, first_round = await service.submit_message(conversation.id, "重复测试", "same-key")
    await service._conversation_tasks[conversation.id]
    second, second_round = await service.submit_message(conversation.id, "重复测试", "same-key")
    assert second.id == first.id
    assert second_round.id == first_round.id


@pytest.mark.asyncio
async def test_next_round_idempotency_key_returns_same_round(harness):
    service, _, _, conversation = harness
    _, first_round = await service.submit_message(conversation.id, "第一轮", "first")
    await service._conversation_tasks[conversation.id]
    next_one = await service.next_round(conversation.id, "next-key")
    next_two = await service.next_round(conversation.id, "next-key")
    assert next_two.id == next_one.id
    await service._conversation_tasks[conversation.id]
    assert next_one.round_number == first_round.round_number + 1


@pytest.mark.asyncio
async def test_free_mode_is_sequential_and_respects_message_cap(harness):
    service, sessions, provider, conversation = harness
    await service.update_conversation(conversation.id, {"mode": "free", "free_max_messages": 2})
    _, round_row = await service.submit_message(conversation.id, "自由讨论", "free-1")
    await service._conversation_tasks[conversation.id]
    assert len(provider.started) == 2
    async with sessions() as session:
        runs = list((await session.execute(__import__('sqlalchemy').select(GenerationRun).where(GenerationRun.round_id == round_row.id))).scalars().all())
        stored_round = await session.get(Round, round_row.id)
    assert len(runs) == 2
    assert all(run.status == "completed" for run in runs)
    assert stored_round is not None
    assert stored_round.status == "completed"
    assert stored_round.stop_reason == "max_messages"
    assert stored_round.completed_count == 2
    assert stored_round.error_count == 0
    assert stored_round.cancelled_count == 0


@pytest.mark.asyncio
async def test_free_mode_is_bounded_to_two_fair_cycles(harness):
    service, sessions, provider, conversation = harness
    await service.update_conversation(conversation.id, {"mode": "free", "free_max_messages": 20})
    _, round_row = await service.submit_message(conversation.id, "围绕这个话题简短交流", "free-cycles")
    await service._conversation_tasks[conversation.id]

    assert len(provider.started) == 6
    async with sessions() as session:
        runs = list((await session.execute(__import__('sqlalchemy').select(GenerationRun).where(GenerationRun.round_id == round_row.id))).scalars().all())
        stored_round = await session.get(Round, round_row.id)
    assert len(runs) == 6
    assert all(run.status == "completed" for run in runs)
    assert stored_round is not None
    assert stored_round.status == "completed"
    assert stored_round.stop_reason == "cycle_limit"
    assert stored_round.completed_count == 6
    assert stored_round.error_count == 0
    assert stored_round.cancelled_count == 0


def test_jimo_session_id_is_stable_but_isolated_per_agent():
    first = _jimo_session_id("conversation-1", "agent-deepseek")
    assert first == _jimo_session_id("conversation-1", "agent-deepseek")
    assert first != _jimo_session_id("conversation-1", "agent-qwen")
