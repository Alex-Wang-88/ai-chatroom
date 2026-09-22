import hashlib
from dataclasses import dataclass

from app.providers.base import ChatMessage

DEFAULT_AGENT_SYSTEM_PROMPT = (
    "像真人一样参与群聊：直接回答，简洁自然，有明确观点，适当回应上一位成员。"
    "通常只写 2-4 句，不要长篇大论、固定模板或复述问题。"
    "不要展示思考过程，不要说‘作为 AI’，只输出最终发言。"
)

FREE_MODE_INSTRUCTION = (
    "围绕用户最后提出的话题发言，先回应上一位成员，再补充一个新观点。"
    "不要引入无关话题、虚构用户回应或提出新的任务。像真人聊天一样自然简短，控制在 2-4 句；"
    "如果没有新观点，就简短总结，不要继续扩展。"
)


@dataclass(slots=True, frozen=True)
class ContextSelection:
    message_ids: list[str]
    transcript: str
    content_hash: str


def _label(message: object) -> str:
    sender = getattr(message, "sender_display_name", "未知成员")
    content = getattr(message, "content", "")
    return f"[{sender}]\n{content}"


def select_recent_messages(messages: list[object], trigger_message_id: str | None, limit: int, budget: int) -> ContextSelection:
    finalized = [message for message in messages if getattr(message, "status", "completed") in {"completed", "error", "cancelled"}]
    chosen: list[object] = []
    used = 0
    for message in reversed(finalized):
        if len(chosen) >= limit:
            break
        rendered = _label(message)
        if used + len(rendered) <= budget or not chosen:
            chosen.append(message)
            used += len(rendered)
    trigger = next((message for message in finalized if getattr(message, "id", None) == trigger_message_id), None)
    if trigger is not None and trigger not in chosen:
        chosen.append(trigger)
    chosen.sort(key=lambda item: (getattr(item, "display_sequence", None) is None, getattr(item, "display_sequence", 0), getattr(item, "created_at", 0)))
    rendered_parts: list[str] = []
    for message in chosen:
        rendered = _label(message)
        if len("\n\n".join(rendered_parts) + rendered) > budget:
            rendered = rendered[-budget:] if budget else rendered
            rendered = "[内容已截断]\n" + rendered
        rendered_parts.append(rendered)
    transcript = "\n\n".join(rendered_parts)
    return ContextSelection(
        message_ids=[str(message.id) for message in chosen],
        transcript=transcript,
        content_hash=hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
    )


def build_provider_messages(
    *,
    agent: object,
    members: list[object],
    transcript: str,
    instruction: str,
) -> list[ChatMessage]:
    member_lines = "\n".join(f"- {getattr(member, 'display_name', '')}" for member in members)
    identity = (
        f"你是 {agent.display_name}。\n"
        "你正在一个多人 AI 群聊中。\n"
        f"群聊成员包括：\n{member_lines}\n\n"
        "历史消息使用 [发送者] 标记。你可以回应用户或其他 AI，"
        "但不要冒充其他成员、替其他成员发言或伪造尚未发生的消息。\n"
        f"你的专属人格设定：\n{agent.system_prompt or DEFAULT_AGENT_SYSTEM_PROMPT}"
    )
    user_content = (
        "<room_transcript>\n"
        f"{transcript}\n"
        "</room_transcript>\n\n"
        "<current_instruction>\n"
        f"{instruction}\n"
        "</current_instruction>"
    )
    return [ChatMessage(role="system", content=identity), ChatMessage(role="user", content=user_content)]
