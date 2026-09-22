import random
from types import SimpleNamespace

from app.orchestrator.context_builder import (
    DEFAULT_AGENT_SYSTEM_PROMPT,
    FREE_MODE_INSTRUCTION,
    build_provider_messages,
    select_recent_messages,
)
from app.orchestrator.mention_parser import parse_mentions
from app.orchestrator.router import route_topic
from app.orchestrator.scheduler import FreeScheduler, SpeakerStat


def agent(name: str, handle: str, aliases: list[str] | None = None, talkativeness: float = 1.0):
    return SimpleNamespace(id=handle, display_name=name, mention_handle=handle, mention_aliases=aliases or [], enabled=True, system_prompt="persona", talkativeness=talkativeness)


def test_mentions_are_parsed_by_backend_rules():
    deepseek = agent("deepseekv4lash", "deepseekv4lash", ["DeepSeek"])
    qwen = agent("千问3.6flash", "qwen36flash", ["Qwen", "千问"])
    result = parse_mentions("@DeepSeek @千问 请比较方案", [deepseek, qwen])
    assert result.handles == ["deepseekv4lash", "qwen36flash"]
    assert result.unknown == []


def test_topic_router_mute_wins_over_mention():
    deepseek = agent("DeepSeek", "deepseekv4lash")
    qwen = agent("Qwen", "qwen36flash")
    links = [SimpleNamespace(agent=deepseek, enabled=True, muted=True), SimpleNamespace(agent=qwen, enabled=True, muted=False)]
    result = route_topic(parse_mentions("@DeepSeek", [deepseek, qwen]), links)
    assert result.selected == []
    assert result.muted == [deepseek]


def test_scheduler_respects_consecutive_limit():
    scheduler = FreeScheduler(max_consecutive=2, rng=random.Random(3))
    first = agent("A", "a")
    second = agent("B", "b")
    stats = {"a": SpeakerStat(consecutive=2), "b": SpeakerStat()}
    assert scheduler.choose([first, second], stats) is second


def test_scheduler_excludes_agents_already_selected_in_cycle():
    scheduler = FreeScheduler(rng=random.Random(3))
    first = agent("A", "a")
    second = agent("B", "b")
    assert scheduler.choose([first, second], {}, excluded_ids={"b"}) is first


def test_context_selection_keeps_trigger_message_and_budget():
    messages = [SimpleNamespace(id=str(i), sender_display_name="用户", content="x" * 20, status="completed", display_sequence=i, created_at=i) for i in range(8)]
    selection = select_recent_messages(messages, "0", limit=3, budget=80)
    assert "[用户]" in selection.transcript
    assert "0" in selection.message_ids or len(selection.transcript) <= 80
    provider_messages = build_provider_messages(agent=agent("A", "a"), members=[agent("A", "a")], transcript=selection.transcript, instruction="reply")
    assert provider_messages[0].role == "system"
    assert "多人 AI 群聊" in provider_messages[0].content


def test_default_agent_prompt_is_conversational_and_concise():
    assert "像真人一样参与群聊" in DEFAULT_AGENT_SYSTEM_PROMPT
    assert "不要展示思考过程" in DEFAULT_AGENT_SYSTEM_PROMPT
    assert "2-4 句" in DEFAULT_AGENT_SYSTEM_PROMPT
    assert "不要引入无关话题" in FREE_MODE_INSTRUCTION
