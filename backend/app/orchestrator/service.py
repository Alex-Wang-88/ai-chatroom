import asyncio
import logging
import random
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db.base import new_id, utc_now
from app.models import (
    Agent,
    ContextSnapshot,
    Conversation,
    ConversationAgent,
    Debate,
    DebateTurn,
    GenerationRun,
    Message,
    Round,
)
from app.orchestrator.cancellation import CancellationRegistry
from app.orchestrator.context_builder import (
    DEFAULT_AGENT_SYSTEM_PROMPT,
    FREE_MODE_INSTRUCTION,
    build_provider_messages,
    select_recent_messages,
)
from app.orchestrator.debate import (
    build_debate_instruction,
    render_debate_history,
)
from app.orchestrator.mention_parser import parse_mentions
from app.orchestrator.router import route_free_priority, route_topic
from app.orchestrator.scheduler import FreeScheduler, SpeakerStat
from app.providers import GenerationConfig, ProviderError, ProviderRegistry
from app.realtime.event_hub import ConversationEventHub

logger = logging.getLogger(__name__)


TERMINAL_RUNS = {"completed", "error", "cancelled"}
TERMINAL_ROUNDS = {"completed", "completed_with_errors", "failed", "cancelled"}
FREE_MODE_MAX_CYCLES = 2


class OrchestratorError(RuntimeError):
    def __init__(self, message: str, code: str = "orchestrator_error", status_code: int = 409):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _model_default(handle: str, settings: Settings) -> str:
    return settings.model_id_for_handle(handle)


def _jimo_session_id(conversation_id: str, agent_id: str) -> str:
    """Return one stable, isolated Jimo session per room member.

    Jimo share sessions are keyed by ``sessionId``. Reusing the room ID for
    all three share URLs can make the provider console merge the requests
    under whichever agent handled the session most recently. Local history is
    still authoritative, but keeping a deterministic per-agent UUID preserves
    useful provider-side session records without creating a new session every
    turn.
    """
    return str(uuid5(NAMESPACE_URL, f"ai-chatroom:jimo:{conversation_id}:{agent_id}"))


def _jimo_debate_session_id(debate_id: str, side: str, agent_id: str) -> str:
    """Keep the provider session isolated for each side of a debate."""
    return _jimo_session_id(f"debate:{debate_id}:{side}", agent_id)


class ConversationOrchestrator:
    def __init__(self, settings: Settings, sessions: async_sessionmaker[AsyncSession], providers: ProviderRegistry, hub: ConversationEventHub):
        self.settings = settings
        self.sessions = sessions
        self.providers = providers
        self.hub = hub
        self.cancellations = CancellationRegistry()
        self._conversation_tasks: dict[str, asyncio.Task] = {}
        self._run_tasks: dict[str, asyncio.Task] = {}
        self._round_cancel_events: dict[str, asyncio.Event] = {}
        self._sequence_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._round_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._sequence_counters: dict[str, int] = {}
        self._buffers: dict[str, str] = {}
        self._agent_states: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self._free_stop_events: dict[str, asyncio.Event] = {}
        self._next_idempotency: dict[str, dict[str, str]] = defaultdict(dict)

    async def seed_agents(self) -> None:
        async with self.sessions() as session:
            existing = (await session.execute(select(Agent))).scalars().all()
            if existing:
                # Upgrade only the original seed/fallback text. A prompt
                # customized through the settings API must remain untouched.
                legacy_prompts = {"", "保持清晰、具体，并回应其他成员的观点。", "保持清晰、具体并尊重其他成员。"}
                changed = False
                for agent in existing:
                    if agent.system_prompt in legacy_prompts:
                        agent.system_prompt = DEFAULT_AGENT_SYSTEM_PROMPT
                        changed = True
                if changed:
                    await session.commit()
                return
            defaults = [
                ("deepseekv4lash", "deepseekv4lash", ["DeepSeek", "deepseek", "deepseekv4flash"]),
                ("千问3.6flash", "qwen36flash", ["Qwen", "千问", "qwen"]),
                ("glm5.3flash", "glm53flash", ["GLM", "glm"]),
            ]
            for display_name, handle, aliases in defaults:
                session.add(
                    Agent(
                        id=new_id(),
                        display_name=display_name,
                        mention_handle=handle,
                        mention_aliases=aliases,
                        provider="jimo",
                        model_id=_model_default(handle, self.settings),
                        system_prompt=DEFAULT_AGENT_SYSTEM_PROMPT,
                    )
                )
            await session.commit()

    async def create_conversation(self, title: str | None = None, mode: str = "topic") -> Conversation:
        async with self.sessions() as session:
            conversation = Conversation(
                id=new_id(),
                title=(title or "新建聊天").strip()[:200] or "新建聊天",
                mode=mode,
                context_message_limit=self.settings.context_message_limit,
                context_character_budget=self.settings.context_character_budget,
                free_max_messages=self.settings.free_max_messages,
                max_consecutive_messages=self.settings.free_max_consecutive_messages,
            )
            session.add(conversation)
            agents = (await session.execute(select(Agent).where(Agent.enabled).order_by(Agent.id))).scalars().all()
            for index, agent in enumerate(agents):
                session.add(ConversationAgent(conversation_id=conversation.id, agent_id=agent.id, sort_order=index))
            await session.commit()
            await session.refresh(conversation)
            await self.hub.publish(conversation.id, "conversation.created", self._conversation_payload(conversation))
            return conversation

    @staticmethod
    def _conversation_payload(conversation: Conversation) -> dict[str, Any]:
        return {
            "id": conversation.id,
            "title": conversation.title,
            "mode": conversation.mode,
            "context_strategy": conversation.context_strategy,
            "context_message_limit": conversation.context_message_limit,
            "context_character_budget": conversation.context_character_budget,
            "free_max_messages": conversation.free_max_messages,
            "max_consecutive_messages": conversation.max_consecutive_messages,
        }

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        async with self.sessions() as session:
            return await session.get(Conversation, conversation_id)

    async def list_conversations(self, limit: int = 50) -> list[Conversation]:
        async with self.sessions() as session:
            return list((await session.execute(select(Conversation).where(Conversation.archived_at.is_(None)).order_by(Conversation.updated_at.desc()).limit(limit))).scalars().all())

    @staticmethod
    def _default_debate_title(topic: str | None, pro_position: str | None, con_position: str | None) -> str:
        if topic:
            return topic[:200]
        pro = " ".join((pro_position or "").split())[:80]
        con = " ".join((con_position or "").split())[:80]
        return f"{pro} / {con}"[:200] or "新建辩论"

    async def create_debate(
        self,
        *,
        title: str | None,
        topic: str | None,
        pro_position: str | None,
        con_position: str | None,
        pro_agent_id: str,
        con_agent_id: str,
    ) -> Debate:
        async with self.sessions() as session:
            pro_agent = await session.get(Agent, pro_agent_id)
            con_agent = await session.get(Agent, con_agent_id)
            if not pro_agent or not con_agent:
                raise OrchestratorError("The selected debate model was not found", "agent_not_found", 404)
            if not pro_agent.enabled or not con_agent.enabled:
                raise OrchestratorError("The selected debate model is disabled", "agent_disabled", 409)

            debate = Debate(
                id=new_id(),
                title=(title or self._default_debate_title(topic, pro_position, con_position)).strip()[:200] or "新建辩论",
                topic=topic,
                pro_position=pro_position,
                con_position=con_position,
                pro_agent_id=pro_agent_id,
                con_agent_id=con_agent_id,
                status="active",
            )
            session.add(debate)
            await session.commit()
            await session.refresh(debate)
            return debate

    async def list_debates(self, limit: int = 50) -> list[Debate]:
        async with self.sessions() as session:
            query = select(Debate).options(selectinload(Debate.turns)).order_by(Debate.updated_at.desc()).limit(limit)
            return list((await session.execute(query)).scalars().all())

    async def get_debate(self, debate_id: str) -> Debate | None:
        async with self.sessions() as session:
            query = select(Debate).options(selectinload(Debate.turns)).where(Debate.id == debate_id)
            return (await session.execute(query)).scalar_one_or_none()

    async def rename_debate(self, debate_id: str, title: str) -> Debate:
        async with self.sessions() as session:
            query = select(Debate).options(selectinload(Debate.turns)).where(Debate.id == debate_id)
            debate = (await session.execute(query)).scalar_one_or_none()
            if not debate:
                raise OrchestratorError("Debate not found", "not_found", 404)
            debate.title = title.strip()[:200]
            debate.updated_at = utc_now()
            await session.commit()
            await session.refresh(debate)
            return debate

    async def end_debate(self, debate_id: str) -> Debate:
        async with self.sessions() as session:
            query = select(Debate).options(selectinload(Debate.turns)).where(Debate.id == debate_id)
            debate = (await session.execute(query)).scalar_one_or_none()
            if not debate:
                raise OrchestratorError("Debate not found", "not_found", 404)
            if debate.status != "ended":
                debate.status = "ended"
                debate.ended_at = utc_now()
                debate.updated_at = debate.ended_at
                await session.commit()
            await session.refresh(debate)
            return debate

    async def save_debate_turn(
        self,
        *,
        debate_id: str,
        turn_number: int,
        side: str,
        content: str,
        agent: Agent,
    ) -> DebateTurn:
        async with self.sessions() as session:
            debate = await session.get(Debate, debate_id)
            if not debate:
                raise OrchestratorError("Debate not found", "not_found", 404)
            if debate.status == "ended":
                raise OrchestratorError("Debate has already ended", "debate_ended", 409)

            existing_query = select(DebateTurn).where(
                DebateTurn.debate_id == debate_id,
                DebateTurn.turn_number == turn_number,
            )
            existing = (await session.execute(existing_query)).scalar_one_or_none()
            if existing:
                if existing.side == side and existing.content == content:
                    return existing
                raise OrchestratorError("Debate history is out of date", "debate_history_conflict", 409)

            last_number = int(
                (await session.execute(select(func.max(DebateTurn.turn_number)).where(DebateTurn.debate_id == debate_id))).scalar()
                or 0
            )
            if turn_number != last_number + 1:
                raise OrchestratorError("Debate history is out of date", "debate_history_conflict", 409)

            turn = DebateTurn(
                id=new_id(),
                debate_id=debate_id,
                turn_number=turn_number,
                side=side,
                content=content,
                agent_id=agent.id,
                display_name=agent.display_name,
                model_id=agent.model_id,
            )
            session.add(turn)
            debate.updated_at = utc_now()
            await session.commit()
            await session.refresh(turn)
            return turn

    async def get_messages(self, conversation_id: str, limit: int = 100, before: datetime | None = None) -> list[Message]:
        async with self.sessions() as session:
            query = select(Message).where(Message.conversation_id == conversation_id)
            if before:
                query = query.where(Message.created_at < before)
            rows = list((await session.execute(query.order_by(Message.created_at.desc()).limit(limit))).scalars().all())
            return list(reversed(rows))

    async def get_links(self, session: AsyncSession, conversation_id: str) -> list[ConversationAgent]:
        query = select(ConversationAgent).options(selectinload(ConversationAgent.agent)).where(ConversationAgent.conversation_id == conversation_id).order_by(ConversationAgent.sort_order)
        return list((await session.execute(query)).scalars().all())

    async def update_conversation(self, conversation_id: str, values: dict[str, Any]) -> Conversation:
        async with self.sessions() as session:
            conversation = await session.get(Conversation, conversation_id)
            if not conversation:
                raise OrchestratorError("Conversation not found", "not_found", 404)
            for key, value in values.items():
                if value is not None and hasattr(conversation, key):
                    setattr(conversation, key, value)
            await session.commit()
            await session.refresh(conversation)
            await self.hub.publish(conversation.id, "conversation.updated", self._conversation_payload(conversation))
            return conversation

    async def archive_conversation(self, conversation_id: str) -> Conversation:
        async with self.sessions() as session:
            conversation = await session.get(Conversation, conversation_id)
            if not conversation:
                raise OrchestratorError("Conversation not found", "not_found", 404)
            if conversation_id in self._conversation_tasks and not self._conversation_tasks[conversation_id].done():
                raise OrchestratorError("Stop the active discussion before archiving", "round_in_progress")
            conversation.archived_at = utc_now()
            conversation.updated_at = conversation.archived_at
            await session.commit()
            await session.refresh(conversation)
            await self.hub.publish(conversation.id, "conversation.updated", self._conversation_payload(conversation))
            return conversation

    async def conversation_agents(self, conversation_id: str) -> list[ConversationAgent]:
        async with self.sessions() as session:
            return await self.get_links(session, conversation_id)

    async def _prepare_debate_generation(
        self,
        *,
        debate_id: str,
        topic: str | None,
        pro_position: str | None,
        con_position: str | None,
        pro_agent_id: str,
        con_agent_id: str,
        side: str,
        history: list[object],
    ) -> tuple[Agent, Any, list[Any], GenerationConfig]:
        if side not in {"pro", "con"}:
            raise OrchestratorError("Invalid debate side", "invalid_debate_side", 400)

        async with self.sessions() as session:
            pro_agent = await session.get(Agent, pro_agent_id)
            con_agent = await session.get(Agent, con_agent_id)

        if not pro_agent or not con_agent:
            raise OrchestratorError("The selected debate model was not found", "agent_not_found", 404)
        selected_agent = pro_agent if side == "pro" else con_agent
        if not selected_agent.enabled:
            raise OrchestratorError("The selected debate model is disabled", "agent_disabled", 409)

        members = [pro_agent] if pro_agent.id == con_agent.id else [pro_agent, con_agent]
        instruction = build_debate_instruction(
            topic=topic,
            pro_position=pro_position,
            con_position=con_position,
            side=side,
            history=history,
        )
        messages = build_provider_messages(
            agent=selected_agent,
            members=members,
            transcript=render_debate_history(history),
            instruction=instruction,
        )
        try:
            provider = self.providers.get(selected_agent.provider)
        except KeyError as exc:
            raise OrchestratorError(
                f"Provider is not configured: {selected_agent.provider}",
                "configuration_error",
                503,
            ) from exc

        provider_extra: dict[str, Any] = {}
        if selected_agent.provider == "jimo":
            share_url = self.settings.share_url_for_handle(selected_agent.mention_handle)
            if share_url:
                provider_extra["endpoint"] = share_url
                provider_extra["session_id"] = _jimo_debate_session_id(debate_id, side, selected_agent.id)
                provider_extra["auth_scheme"] = "raw"

        config = GenerationConfig(
            model=selected_agent.model_id,
            temperature=selected_agent.temperature,
            max_output_tokens=selected_agent.max_output_tokens,
            stream=True,
            extra=provider_extra,
        )
        return selected_agent, provider, messages, config

    async def generate_debate_response(
        self,
        *,
        debate_id: str,
        topic: str | None,
        pro_position: str | None,
        con_position: str | None,
        pro_agent_id: str,
        con_agent_id: str,
        side: str,
        history: list[object],
        persist: bool = False,
    ) -> tuple[str, Agent]:
        """Generate one manually-triggered side of a debate."""
        selected_agent, provider, messages, config = await self._prepare_debate_generation(
            debate_id=debate_id,
            topic=topic,
            pro_position=pro_position,
            con_position=con_position,
            pro_agent_id=pro_agent_id,
            con_agent_id=con_agent_id,
            side=side,
            history=history,
        )
        buffer = ""
        try:
            async for chunk in provider.stream_chat(messages, config, asyncio.Event()):
                if chunk.text:
                    buffer += chunk.text
                if chunk.done:
                    break
        except ProviderError as exc:
            raise OrchestratorError(str(exc), exc.error_type, exc.status_code or 502) from exc

        content = buffer.strip()
        if not content:
            raise OrchestratorError("The selected model returned no content", "empty_response", 502)
        if persist:
            await self.save_debate_turn(
                debate_id=debate_id,
                turn_number=len(history) + 1,
                side=side,
                content=content,
                agent=selected_agent,
            )
        return content, selected_agent

    async def stream_debate_response(
        self,
        *,
        debate_id: str,
        topic: str | None,
        pro_position: str | None,
        con_position: str | None,
        pro_agent_id: str,
        con_agent_id: str,
        side: str,
        history: list[object],
        persist: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield provider output as debate SSE-ready events."""
        try:
            selected_agent, provider, messages, config = await self._prepare_debate_generation(
                debate_id=debate_id,
                topic=topic,
                pro_position=pro_position,
                con_position=con_position,
                pro_agent_id=pro_agent_id,
                con_agent_id=con_agent_id,
                side=side,
                history=history,
            )
            yield {
                "event": "start",
                "side": side,
                "agent_id": selected_agent.id,
                "display_name": selected_agent.display_name,
                "model_id": selected_agent.model_id,
            }
            raw_buffer = ""
            cancellation_event = asyncio.Event()
            try:
                async for chunk in provider.stream_chat(messages, config, cancellation_event):
                    if chunk.text:
                        raw_buffer += chunk.text
                        yield {"event": "delta", "text": chunk.text}
                    if chunk.done:
                        break
            except ProviderError as exc:
                raise OrchestratorError(str(exc), exc.error_type, exc.status_code or 502) from exc

            content = raw_buffer.strip()
            if not content:
                raise OrchestratorError("The selected model returned no content", "empty_response", 502)
            if persist:
                await self.save_debate_turn(
                    debate_id=debate_id,
                    turn_number=len(history) + 1,
                    side=side,
                    content=content,
                    agent=selected_agent,
                )
            yield {
                "event": "done",
                "side": side,
                "content": content,
                "agent_id": selected_agent.id,
                "display_name": selected_agent.display_name,
                "model_id": selected_agent.model_id,
            }
        except OrchestratorError as exc:
            yield {"event": "error", "code": exc.code, "message": str(exc)}
        except Exception:
            logger.exception("debate generation failed debate_id=%s side=%s", debate_id, side)
            yield {"event": "error", "code": "internal_error", "message": "模型响应失败，请重试"}

    async def update_agent_settings(self, conversation_id: str, agent_id: str, values: dict[str, Any]) -> ConversationAgent:
        async with self.sessions() as session:
            query = select(ConversationAgent).options(selectinload(ConversationAgent.agent)).where(
                ConversationAgent.conversation_id == conversation_id, ConversationAgent.agent_id == agent_id
            )
            link = (await session.execute(query)).scalar_one_or_none()
            if not link:
                raise OrchestratorError("Agent is not in this conversation", "not_found", 404)
            for key, value in values.items():
                if value is not None and hasattr(link, key):
                    setattr(link, key, value)
            await session.commit()
            await session.refresh(link)
            await self.hub.publish(
                conversation_id,
                "conversation_agent.updated",
                {"agent_id": agent_id, "muted": link.muted, "enabled": link.enabled, "sort_order": link.sort_order},
            )
            return link

    async def update_agent(self, agent_id: str, values: dict[str, Any]) -> Agent:
        async with self.sessions() as session:
            agent = await session.get(Agent, agent_id)
            if not agent:
                raise OrchestratorError("Agent not found", "not_found", 404)
            for key, value in values.items():
                if value is not None and hasattr(agent, key):
                    setattr(agent, key, value)
            await session.commit()
            await session.refresh(agent)
            return agent

    async def submit_message(self, conversation_id: str, content: str, client_message_id: str | None = None) -> tuple[Message, Round]:
        async with self.sessions() as session:
            conversation = await session.get(Conversation, conversation_id)
            if not conversation:
                raise OrchestratorError("Conversation not found", "not_found", 404)
            if conversation_id in self._conversation_tasks and not self._conversation_tasks[conversation_id].done():
                raise OrchestratorError("A round is already running", "round_in_progress")
            if client_message_id:
                existing = (await session.execute(select(Message).where(Message.conversation_id == conversation_id, Message.client_message_id == client_message_id))).scalar_one_or_none()
                if existing:
                    round_row = await session.get(Round, existing.round_id) if existing.round_id else None
                    if round_row:
                        return existing, round_row
            async with self._sequence_locks[conversation_id]:
                sequence = await self._next_sequence(session, conversation_id)
                user_message = Message(
                    id=new_id(), conversation_id=conversation_id, sender_type="user", sender_id=None,
                    sender_display_name="用户", content=content, status="completed", display_sequence=sequence,
                    client_message_id=client_message_id, created_at=utc_now(), finished_at=utc_now(),
                )
                session.add(user_message)
                await session.flush()
                round_row = await self._create_round(session, conversation, user_message, mode=conversation.mode)
                conversation.updated_at = utc_now()
                await session.commit()
                await session.refresh(user_message)
                await session.refresh(round_row)
            task = asyncio.create_task(self._run_round(round_row.id, conversation_id, content, user_message.id))
            self._conversation_tasks[conversation_id] = task
            return user_message, round_row

    async def next_round(self, conversation_id: str, idempotency_key: str | None = None) -> Round:
        async with self.sessions() as session:
            conversation = await session.get(Conversation, conversation_id)
            if not conversation:
                raise OrchestratorError("Conversation not found", "not_found", 404)
            if idempotency_key:
                existing_round_id = self._next_idempotency[conversation_id].get(idempotency_key)
                if existing_round_id:
                    existing_round = await session.get(Round, existing_round_id)
                    if existing_round:
                        return existing_round
            if conversation_id in self._conversation_tasks and not self._conversation_tasks[conversation_id].done():
                raise OrchestratorError("A round is already running", "round_in_progress")
            last_round = (await session.execute(select(Round).where(Round.conversation_id == conversation_id).order_by(Round.round_number.desc()).limit(1))).scalar_one_or_none()
            if not last_round or last_round.status not in {"completed", "completed_with_errors"}:
                raise OrchestratorError("The previous round is not ready for next step", "round_not_ready")
            trigger = await session.get(Message, last_round.trigger_message_id) if last_round.trigger_message_id else None
            if not trigger:
                raise OrchestratorError("Round has no trigger message", "round_invalid", 500)
            round_row = await self._create_round(session, conversation, trigger, mode=conversation.mode)
            conversation.updated_at = utc_now()
            await session.commit()
            await session.refresh(round_row)
            if idempotency_key:
                self._next_idempotency[conversation_id][idempotency_key] = round_row.id
            task = asyncio.create_task(self._run_round(round_row.id, conversation_id, trigger.content, trigger.id))
            self._conversation_tasks[conversation_id] = task
            return round_row

    async def _next_sequence(self, session: AsyncSession, conversation_id: str) -> int:
        current = self._sequence_counters.get(conversation_id)
        if current is None:
            current = int((await session.execute(select(func.max(Message.display_sequence)).where(Message.conversation_id == conversation_id))).scalar() or 0)
        current += 1
        self._sequence_counters[conversation_id] = current
        return current

    async def _create_round(self, session: AsyncSession, conversation: Conversation, trigger: Message, mode: str) -> Round:
        last_number = int((await session.execute(select(func.max(Round.round_number)).where(Round.conversation_id == conversation.id))).scalar() or 0)
        round_row = Round(
            id=new_id(), conversation_id=conversation.id, round_number=last_number + 1, mode=mode,
            trigger_message_id=trigger.id, status="round_created", started_at=utc_now(),
        )
        session.add(round_row)
        await session.flush()
        trigger.round_id = round_row.id
        return round_row

    async def _make_snapshot(self, session: AsyncSession, conversation: Conversation, trigger_id: str, instruction: str) -> tuple[ContextSnapshot, list[Message]]:
        messages = list((await session.execute(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at, Message.id))).scalars().all())
        selection = select_recent_messages(messages, trigger_id, conversation.context_message_limit, conversation.context_character_budget)
        snapshot = ContextSnapshot(
            id=new_id(), conversation_id=conversation.id, strategy=conversation.context_strategy, version=1,
            cutoff_message_id=trigger_id, message_ids=selection.message_ids, serialized_transcript=selection.transcript,
            character_count=len(selection.transcript), content_hash=selection.content_hash, created_at=utc_now(),
        )
        session.add(snapshot)
        await session.flush()
        return snapshot, messages

    async def _run_round(self, round_id: str, conversation_id: str, trigger_content: str, trigger_id: str) -> None:
        try:
            conversation = await self.get_conversation(conversation_id)
            if not conversation:
                await self._mark_round(round_id, "failed", stop_reason="conversation_not_found")
                return
            if conversation.mode == "free":
                await self._run_free(round_id, conversation_id, trigger_content, trigger_id)
            else:
                await self._run_topic(round_id, conversation_id, trigger_content, trigger_id)
        except Exception:
            logger.exception("round crashed conversation_id=%s round_id=%s", conversation_id, round_id)
            await self._mark_round(round_id, "failed", stop_reason="internal_error")
        finally:
            self._conversation_tasks.pop(conversation_id, None)

    async def _prepare_topic_runs(self, round_id: str, conversation_id: str, trigger_id: str, trigger_content: str) -> list[str]:
        async with self.sessions() as session:
            round_row = await session.get(Round, round_id)
            conversation = await session.get(Conversation, conversation_id)
            if not round_row or not conversation:
                return []
            links = await self.get_links(session, conversation_id)
            messages = list((await session.execute(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at, Message.id))).scalars().all())
            mentions = parse_mentions(trigger_content, [link.agent for link in links])
            routing = route_topic(mentions, links)
            if not routing.selected:
                if mentions.handles and routing.muted:
                    await self.hub.publish(conversation_id, "warning.mention_rejected", {"reason": "agent_muted", "agents": [agent.display_name for agent in routing.muted]})
                if mentions.handles and mentions.unknown:
                    await self.hub.publish(conversation_id, "warning.mention_rejected", {"reason": "unknown_agent", "handles": mentions.unknown})
                raise OrchestratorError("No eligible agents for this message", "no_eligible_agents")
            selection = select_recent_messages(messages, trigger_id, conversation.context_message_limit, conversation.context_character_budget)
            snapshot = ContextSnapshot(
                id=new_id(), conversation_id=conversation_id, strategy=conversation.context_strategy, version=1,
                cutoff_message_id=trigger_id, message_ids=selection.message_ids, serialized_transcript=selection.transcript,
                character_count=len(selection.transcript), content_hash=selection.content_hash, created_at=utc_now(),
            )
            session.add(snapshot)
            await session.flush()
            round_row.context_snapshot_id = snapshot.id
            round_row.status = "generating"
            run_ids: list[str] = []
            for agent in routing.selected:
                message = Message(
                    id=new_id(), conversation_id=conversation_id, round_id=round_id, sender_type="agent", sender_id=agent.id,
                    sender_display_name=agent.display_name, content="", status="pending", display_sequence=None,
                    created_at=utc_now(),
                )
                session.add(message)
                await session.flush()
                run = GenerationRun(
                    id=new_id(), conversation_id=conversation_id, round_id=round_id, message_id=message.id,
                    agent_id=agent.id, provider=agent.provider, model_id=agent.model_id,
                    attempt_number=1, context_snapshot_id=snapshot.id, status="pending",
                )
                session.add(run)
                run_ids.append(run.id)
                self._agent_states[conversation_id][agent.id] = {"availability": "enabled", "activity": "thinking", "effective_state": "thinking", "run_id": run.id}
            await session.commit()
            await self.hub.publish(conversation_id, "round.started", {"round_id": round_id, "mode": "topic", "participant_count": len(run_ids), "context_snapshot_id": snapshot.id})
            if mentions.handles:
                for agent in routing.muted:
                    await self.hub.publish(conversation_id, "warning.mention_rejected", {"reason": "agent_muted", "agents": [agent.display_name]})
                if mentions.unknown:
                    await self.hub.publish(conversation_id, "warning.mention_rejected", {"reason": "unknown_agent", "handles": mentions.unknown})
            return run_ids

    async def _run_topic(self, round_id: str, conversation_id: str, trigger_content: str, trigger_id: str) -> None:
        try:
            run_ids = await self._prepare_topic_runs(round_id, conversation_id, trigger_id, trigger_content)
        except OrchestratorError as exc:
            await self._mark_round(round_id, "failed", stop_reason=exc.code)
            return
        cancel_event = asyncio.Event()
        self._round_cancel_events[round_id] = cancel_event
        tasks = []
        for run_id in run_ids:
            task = asyncio.create_task(self._run_generation(run_id, cancel_event))
            self._run_tasks[run_id] = task
            tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._finish_round(round_id)
        self._round_cancel_events.pop(round_id, None)

    async def _prepare_free_turn(self, round_id: str, conversation_id: str, agent: Agent, instruction: str, trigger_id: str) -> str:
        async with self.sessions() as session:
            conversation = await session.get(Conversation, conversation_id)
            round_row = await session.get(Round, round_id)
            if not conversation or not round_row:
                raise OrchestratorError("Round not found", "not_found", 404)
            snapshot, _messages = await self._make_snapshot(session, conversation, trigger_id, instruction)
            round_row.context_snapshot_id = snapshot.id
            message = Message(
                id=new_id(), conversation_id=conversation_id, round_id=round_id, sender_type="agent", sender_id=agent.id,
                sender_display_name=agent.display_name, content="", status="pending", display_sequence=None, created_at=utc_now(),
            )
            session.add(message)
            await session.flush()
            run = GenerationRun(
                id=new_id(), conversation_id=conversation_id, round_id=round_id, message_id=message.id, agent_id=agent.id,
                provider=agent.provider, model_id=agent.model_id, attempt_number=1, context_snapshot_id=snapshot.id, status="pending",
            )
            session.add(run)
            round_row.status = "generating"
            await session.commit()
            self._agent_states[conversation_id][agent.id] = {"availability": "enabled", "activity": "thinking", "effective_state": "thinking", "run_id": run.id}
            await self.hub.publish(conversation_id, "free_mode.speaker_selected", {"round_id": round_id, "agent_id": agent.id, "run_id": run.id})
            return run.id

    async def _run_free(self, round_id: str, conversation_id: str, trigger_content: str, trigger_id: str) -> None:
        stop_event = asyncio.Event()
        self._free_stop_events[round_id] = stop_event
        stats: dict[str, SpeakerStat] = {}
        conversation = await self.get_conversation(conversation_id)
        if not conversation:
            await self._mark_round(round_id, "failed", stop_reason="conversation_not_found")
            return
        scheduler = FreeScheduler(max_consecutive=conversation.max_consecutive_messages, rng=random.Random())
        priority_handles: list[str] = []
        consecutive_errors = 0
        await self.hub.publish(
            conversation_id,
            "free_mode.started",
            {
                "round_id": round_id,
                "max_messages": conversation.free_max_messages,
                "max_cycles": FREE_MODE_MAX_CYCLES,
            },
        )
        try:
            async with self.sessions() as session:
                links = await self.get_links(session, conversation_id)
                mention_result = parse_mentions(trigger_content, [link.agent for link in links])
                priority, muted = route_free_priority(mention_result, links)
                priority_handles = [agent.mention_handle for agent in priority]
                if muted:
                    await self.hub.publish(conversation_id, "warning.mention_rejected", {"reason": "agent_muted", "agents": [agent.display_name for agent in muted]})
        except Exception:  # noqa: BLE001 - routing failures must converge the round
            await self._mark_round(round_id, "failed", stop_reason="routing_error")
            return
        generated = 0
        completed_cycles = 0
        cycle_spoken: set[str] = set()
        had_errors = False
        final_status: str | None = None
        final_reason: str | None = None
        try:
            while generated < conversation.free_max_messages and not stop_event.is_set():
                async with self.sessions() as session:
                    links = await self.get_links(session, conversation_id)
                enabled_agents = [link.agent for link in links if link.enabled and link.agent.enabled and not link.muted]
                eligible_ids = {agent.id for agent in enabled_agents}
                cycle_spoken.intersection_update(eligible_ids)
                if not enabled_agents:
                    final_status = "completed_with_errors" if generated else "failed"
                    final_reason = "no_eligible_speaker"
                    break
                if eligible_ids.issubset(cycle_spoken):
                    completed_cycles += 1
                    cycle_spoken.clear()
                    if completed_cycles >= FREE_MODE_MAX_CYCLES:
                        final_status = "completed_with_errors" if had_errors else "completed"
                        final_reason = "cycle_limit"
                        break
                agent = None
                while priority_handles and agent is None:
                    handle = priority_handles.pop(0)
                    agent = next(
                        (
                            candidate
                            for candidate in enabled_agents
                            if candidate.mention_handle == handle and candidate.id not in cycle_spoken
                        ),
                        None,
                    )
                if agent is None:
                    agent = scheduler.choose(enabled_agents, stats, excluded_ids=cycle_spoken)
                if agent is None:
                    final_status = "completed_with_errors" if generated else "failed"
                    final_reason = "no_eligible_speaker"
                    break
                cycle_spoken.add(agent.id)
                run_id = await self._prepare_free_turn(round_id, conversation_id, agent, FREE_MODE_INSTRUCTION, trigger_id)
                self._run_tasks[run_id] = asyncio.create_task(self._run_generation(run_id, stop_event))
                await self._run_tasks[run_id]
                status = await self._run_status(run_id)
                if status == "completed":
                    generated += 1
                    FreeScheduler.record_speaker(stats, agent.id, [candidate.id for candidate in enabled_agents])
                    consecutive_errors = 0
                else:
                    had_errors = True
                    consecutive_errors += 1
                    if consecutive_errors >= self.settings.free_error_threshold:
                        final_status = "completed_with_errors" if generated else "failed"
                        final_reason = "error_threshold"
                        break
            if final_status is None:
                if stop_event.is_set():
                    final_status = "cancelled"
                    final_reason = "user_stopped"
                elif generated >= conversation.free_max_messages:
                    final_status = "completed_with_errors" if had_errors else "completed"
                    final_reason = "max_messages"
                else:
                    final_status = "completed_with_errors" if generated else "failed"
                    final_reason = "no_eligible_speaker"
            await self._mark_round(round_id, final_status, stop_reason=final_reason)
        finally:
            self._free_stop_events.pop(round_id, None)
            async with self.sessions() as session:
                round_row = await session.get(Round, round_id)
                stop_payload = {
                    "round_id": round_id,
                    "generated_messages": generated,
                    "completed_cycles": completed_cycles,
                    "status": round_row.status if round_row else final_status,
                    "stop_reason": round_row.stop_reason if round_row else final_reason,
                    "completed_count": round_row.completed_count if round_row else 0,
                    "error_count": round_row.error_count if round_row else 0,
                    "cancelled_count": round_row.cancelled_count if round_row else 0,
                }
            await self.hub.publish(conversation_id, "free_mode.stopped", stop_payload)

    async def _run_generation(self, run_id: str, round_cancel_event: asyncio.Event) -> None:
        started = time.monotonic()
        self.cancellations.create(run_id)
        async with self.sessions() as session:
            run = (await session.execute(select(GenerationRun).options(selectinload(GenerationRun.message), selectinload(GenerationRun.context_snapshot)).where(GenerationRun.id == run_id))).scalar_one_or_none()
            if not run:
                await self._cleanup_generation(run_id, started)
                return
            agent = await session.get(Agent, run.agent_id)
            conversation = await session.get(Conversation, run.conversation_id)
            links = await self.get_links(session, run.conversation_id)
            snapshot = run.context_snapshot
            run.status = "generating"
            run.request_started_at = utc_now()
            await session.commit()
        if not agent or not conversation or not snapshot:
            await self._set_run_error(run_id, "configuration_error", "Generation context is missing")
            await self._cleanup_generation(run_id, started)
            return
        members = [link.agent for link in links]
        instruction = "请回答用户的问题，并在必要时回应其他成员。"
        if conversation.mode == "free":
            instruction = FREE_MODE_INSTRUCTION
        messages = build_provider_messages(agent=agent, members=members, transcript=snapshot.serialized_transcript, instruction=instruction)
        try:
            provider = self.providers.get(run.provider)
        except KeyError:
            await self._set_run_error(run_id, "configuration_error", f"Provider is not configured: {run.provider}")
            await self._cleanup_generation(run_id, started)
            return
        provider_extra: dict[str, Any] = {}
        if run.provider == "jimo":
            share_url = self.settings.share_url_for_handle(agent.mention_handle)
            if share_url:
                provider_extra["endpoint"] = share_url
                provider_extra["session_id"] = _jimo_session_id(run.conversation_id, run.agent_id)
                # The documented /v2/share flow accepts the supplied value as
                # the Authorization header. /v1 fallback remains Bearer.
                provider_extra["auth_scheme"] = "raw"
        config = GenerationConfig(
            model=run.model_id,
            temperature=agent.temperature,
            max_output_tokens=agent.max_output_tokens,
            stream=True,
            extra=provider_extra,
        )
        cancellation_event = self.cancellations.event_for(run_id)
        buffer = ""
        first_token = False
        delta_index = 0
        last_checkpoint = time.monotonic()
        try:
            await self.hub.publish(run.conversation_id, "generation.started", {"run_id": run_id, "message_id": run.message_id, "agent_id": run.agent_id, "model_id": run.model_id})
            await self.hub.publish(run.conversation_id, "agent.state_changed", {"agent_id": run.agent_id, "activity": "thinking", "effective_state": "thinking", "run_id": run_id})
            async for chunk in provider.stream_chat(messages, config, cancellation_event):
                if round_cancel_event.is_set() or cancellation_event.is_set():
                    break
                if chunk.text:
                    buffer += chunk.text
                    delta_index += 1
                    if not first_token:
                        first_token = True
                        async with self._sequence_locks[run.conversation_id], self.sessions() as sequence_session:
                            sequence = await self._next_sequence(sequence_session, run.conversation_id)
                            await sequence_session.commit()
                        await self._set_first_token(run_id, sequence)
                        await self.hub.publish(run.conversation_id, "generation.first_token", {"run_id": run_id, "message_id": run.message_id, "agent_id": run.agent_id})
                        await self.hub.publish(run.conversation_id, "message.created", {"message_id": run.message_id, "round_id": run.round_id, "agent_id": run.agent_id, "sender_display_name": agent.display_name, "status": "streaming", "display_sequence": sequence, "content": chunk.text, "delta_index": delta_index, "cumulative_length": len(buffer)})
                        await self.hub.publish(run.conversation_id, "agent.state_changed", {"agent_id": run.agent_id, "activity": "streaming", "effective_state": "streaming", "run_id": run_id})
                    else:
                        await self.hub.publish(run.conversation_id, "message.delta", {"message_id": run.message_id, "agent_id": run.agent_id, "delta": chunk.text, "delta_index": delta_index, "cumulative_length": len(buffer)})
                    if len(buffer) >= 256 and time.monotonic() - last_checkpoint >= 1.0:
                        await self._checkpoint(run_id, buffer)
                        last_checkpoint = time.monotonic()
                if chunk.input_tokens is not None or chunk.output_tokens is not None:
                    await self._set_usage(run_id, chunk.input_tokens, chunk.output_tokens)
                if chunk.provider_request_id:
                    await self._set_provider_request_id(run_id, chunk.provider_request_id)
                if chunk.done:
                    break
            if round_cancel_event.is_set() or cancellation_event.is_set():
                await self._set_run_terminal(run_id, "cancelled", buffer, "cancelled")
            else:
                await self._set_run_terminal(run_id, "completed", buffer, None)
        except ProviderError as exc:
            await self._set_run_terminal(run_id, "error", buffer, exc.error_type, str(exc))
        except asyncio.CancelledError:
            await self._set_run_terminal(run_id, "cancelled", buffer, "cancelled")
            raise
        except Exception:
            logger.exception("generation failed run_id=%s", run_id)
            await self._set_run_terminal(run_id, "error", buffer, "internal_error", "Unexpected generation error")
        finally:
            await self._cleanup_generation(run_id, started)

    async def _cleanup_generation(self, run_id: str, started: float) -> None:
        self._buffers.pop(run_id, None)
        self.cancellations.remove(run_id)
        self._run_tasks.pop(run_id, None)
        elapsed = (time.monotonic() - started) * 1000
        await self._set_duration(run_id, elapsed)

    async def _set_first_token(self, run_id: str, sequence: int) -> None:
        async with self.sessions() as session:
            run = await session.get(GenerationRun, run_id)
            if not run:
                return
            now = utc_now()
            run.first_token_at = now
            run.status = "streaming"
            message = await session.get(Message, run.message_id)
            if message:
                message.first_token_at = now
                message.display_sequence = sequence
                message.status = "streaming"
            await session.commit()

    async def _checkpoint(self, run_id: str, content: str) -> None:
        self._buffers[run_id] = content
        async with self.sessions() as session:
            run = await session.get(GenerationRun, run_id)
            if run:
                message = await session.get(Message, run.message_id)
                if message and message.status not in TERMINAL_RUNS:
                    message.content = content
                    await session.commit()

    async def _set_run_terminal(self, run_id: str, status: str, content: str, error_type: str | None, error_message: str | None = None) -> None:
        async with self.sessions() as session:
            run = await session.get(GenerationRun, run_id)
            if not run:
                return
            now = utc_now()
            run.status = status
            run.finished_at = now
            if error_type:
                run.error_type = error_type
                run.error_message = (error_message or error_type)[:1000]
            message = await session.get(Message, run.message_id)
            if message:
                message.content = content
                message.status = status
                message.finished_at = now
                if status == "error" and message.display_sequence is None:
                    async with self._sequence_locks[run.conversation_id]:
                        message.display_sequence = await self._next_sequence(session, run.conversation_id)
                conversation = await session.get(Conversation, run.conversation_id)
                if conversation:
                    conversation.updated_at = now
                await session.commit()
            else:
                conversation = await session.get(Conversation, run.conversation_id)
                if conversation:
                    conversation.updated_at = now
                await session.commit()
            event_type = "message.completed" if status == "completed" else "message.cancelled" if status == "cancelled" else "message.error"
            await self.hub.publish(run.conversation_id, event_type, {"message_id": run.message_id, "run_id": run_id, "agent_id": run.agent_id, "content": content, "status": status, "error_type": error_type, "error_message": (error_message or "")[:1000]})
            await self.hub.publish(run.conversation_id, "generation." + status, {"run_id": run_id, "message_id": run.message_id, "agent_id": run.agent_id})
            activity = "error" if status == "error" else "cancelled" if status == "cancelled" else "idle"
            await self.hub.publish(run.conversation_id, "agent.state_changed", {"agent_id": run.agent_id, "activity": activity, "effective_state": activity, "run_id": run_id})

    async def _set_run_error(self, run_id: str, error_type: str, error_message: str) -> None:
        await self._set_run_terminal(run_id, "error", "", error_type, error_message)

    async def _set_usage(self, run_id: str, input_tokens: int | None, output_tokens: int | None) -> None:
        async with self.sessions() as session:
            run = await session.get(GenerationRun, run_id)
            if run:
                if input_tokens is not None:
                    run.input_tokens = int(input_tokens)
                if output_tokens is not None:
                    run.output_tokens = int(output_tokens)
                await session.commit()

    async def _set_provider_request_id(self, run_id: str, provider_request_id: str) -> None:
        async with self.sessions() as session:
            run = await session.get(GenerationRun, run_id)
            if run:
                run.provider_request_id = provider_request_id[:200]
                await session.commit()

    async def _set_duration(self, run_id: str, duration_ms: float) -> None:
        async with self.sessions() as session:
            run = await session.get(GenerationRun, run_id)
            if run:
                run.generation_duration_ms = duration_ms
                if run.first_token_at and run.request_started_at:
                    run.time_to_first_token_ms = (run.first_token_at - run.request_started_at).total_seconds() * 1000
                if run.output_tokens and duration_ms > 0:
                    run.tokens_per_second = run.output_tokens / (duration_ms / 1000)
                await session.commit()

    async def _run_status(self, run_id: str) -> str | None:
        async with self.sessions() as session:
            run = await session.get(GenerationRun, run_id)
            return run.status if run else None

    async def _update_round_counts(self, session: AsyncSession, round_row: Round) -> list[str]:
        runs = list(
            (
                await session.execute(
                    select(GenerationRun.message_id, GenerationRun.attempt_number, GenerationRun.status).where(
                        GenerationRun.round_id == round_row.id
                    )
                )
            ).all()
        )
        latest_by_message: dict[str, tuple[int, str]] = {}
        for message_id, attempt_number, status in runs:
            previous = latest_by_message.get(message_id)
            if previous is None or attempt_number > previous[0]:
                latest_by_message[message_id] = (attempt_number, status)
        statuses = [status for _, status in latest_by_message.values()]
        round_row.completed_count = statuses.count("completed")
        round_row.error_count = statuses.count("error")
        round_row.cancelled_count = statuses.count("cancelled")
        return statuses

    async def _finish_round(self, round_id: str) -> None:
        async with self.sessions() as session:
            round_row = await session.get(Round, round_id)
            if not round_row:
                return
            statuses = await self._update_round_counts(session, round_row)
            if round_row.status == "cancelled":
                final = "cancelled"
            elif not statuses or not any(status == "completed" for status in statuses):
                final = "failed"
            elif any(status != "completed" for status in statuses):
                final = "completed_with_errors"
            else:
                final = "completed"
            round_row.status = final
            round_row.finished_at = utc_now()
            conversation = await session.get(Conversation, round_row.conversation_id)
            if conversation:
                conversation.updated_at = round_row.finished_at
            await session.commit()
            event_type = "round.cancelled" if final == "cancelled" else "round.completed"
            await self.hub.publish(
                round_row.conversation_id,
                event_type,
                {
                    "round_id": round_id,
                    "status": final,
                    "stop_reason": round_row.stop_reason,
                    "completed_count": round_row.completed_count,
                    "error_count": round_row.error_count,
                    "cancelled_count": round_row.cancelled_count,
                },
            )

    async def _mark_round(self, round_id: str, status: str, stop_reason: str | None = None) -> None:
        async with self.sessions() as session:
            round_row = await session.get(Round, round_id)
            if not round_row:
                return
            await self._update_round_counts(session, round_row)
            round_row.status = status
            round_row.stop_reason = stop_reason
            round_row.finished_at = utc_now()
            conversation = await session.get(Conversation, round_row.conversation_id)
            if conversation:
                conversation.updated_at = round_row.finished_at
            await session.commit()
            event_type = "round.cancelled" if status == "cancelled" else "round.completed"
            await self.hub.publish(
                round_row.conversation_id,
                event_type,
                {
                    "round_id": round_id,
                    "status": status,
                    "stop_reason": stop_reason,
                    "completed_count": round_row.completed_count,
                    "error_count": round_row.error_count,
                    "cancelled_count": round_row.cancelled_count,
                },
            )

    async def cancel_generation(self, run_id: str) -> bool:
        return self.cancellations.cancel(run_id)

    async def cancel_round(self, round_id: str) -> None:
        async with self.sessions() as session:
            round_row = await session.get(Round, round_id)
            if not round_row:
                raise OrchestratorError("Round not found", "not_found", 404)
            round_row.status = "cancelled"
            round_row.stop_reason = "user_stopped"
            round_row.finished_at = utc_now()
            conversation = await session.get(Conversation, round_row.conversation_id)
            if conversation:
                conversation.updated_at = round_row.finished_at
            await session.commit()
            run_ids = list((await session.execute(select(GenerationRun.id).where(GenerationRun.round_id == round_id, GenerationRun.status.not_in(TERMINAL_RUNS)))).scalars().all())
        if event := self._round_cancel_events.get(round_id):
            event.set()
        if event := self._free_stop_events.get(round_id):
            event.set()
        self.cancellations.cancel_all(run_ids)
        await self.hub.publish(round_row.conversation_id, "round.cancelled", {"round_id": round_id, "run_ids": run_ids})

    async def retry_message(self, message_id: str) -> GenerationRun:
        async with self.sessions() as session:
            message = await session.get(Message, message_id)
            if not message or not message.round_id or message.sender_type != "agent":
                raise OrchestratorError("Retry target is invalid", "invalid_retry", 400)
            if message.status not in {"error", "cancelled"}:
                raise OrchestratorError("Only failed or cancelled messages can be retried", "invalid_retry")
            run_count = int((await session.execute(select(func.count(GenerationRun.id)).where(GenerationRun.message_id == message_id))).scalar() or 0)
            run = GenerationRun(
                id=new_id(), conversation_id=message.conversation_id, round_id=message.round_id, message_id=message.id,
                agent_id=message.sender_id, provider="jimo", model_id="", attempt_number=run_count + 1,
                status="pending",
            )
            agent = await session.get(Agent, message.sender_id)
            if agent:
                run.provider, run.model_id = agent.provider, agent.model_id
            previous = (await session.execute(select(GenerationRun).where(GenerationRun.message_id == message_id).order_by(GenerationRun.attempt_number.desc()).limit(1))).scalar_one_or_none()
            run.context_snapshot_id = previous.context_snapshot_id if previous else None
            message.retry_count += 1
            message.status = "pending"
            message.content = ""
            session.add(run)
            await session.commit()
            task = asyncio.create_task(self._run_generation(run.id, self._round_cancel_events.get(message.round_id, asyncio.Event())))
            self._run_tasks[run.id] = task
            return run

    async def active_state(self, conversation_id: str) -> dict[str, Any]:
        async with self.sessions() as session:
            round_row = (await session.execute(select(Round).where(Round.conversation_id == conversation_id, Round.status.not_in(TERMINAL_ROUNDS)).order_by(Round.round_number.desc()).limit(1))).scalar_one_or_none()
            messages = list((await session.execute(select(Message).where(Message.conversation_id == conversation_id, Message.status.in_(["pending", "streaming"])).order_by(Message.created_at))).scalars().all())
            return {"round": round_row, "messages": messages, "agent_states": self._agent_states.get(conversation_id, {})}
