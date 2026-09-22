from collections.abc import Sequence

DEBATE_HISTORY_CHARACTER_BUDGET = 24000


def _value(turn: object, name: str) -> str:
    if isinstance(turn, dict):
        return str(turn.get(name, ""))
    return str(getattr(turn, name, ""))


def _side_label(side: str) -> str:
    return "正方" if side == "pro" else "反方"


def render_debate_history(history: Sequence[object]) -> str:
    if not history:
        return "（暂无历史发言，这是开篇立论。）"

    rendered = "\n\n".join(
        f"[{_side_label(_value(turn, 'side'))} 第 {index + 1} 次发言]\n{_value(turn, 'content')}"
        for index, turn in enumerate(history)
    )
    if len(rendered) <= DEBATE_HISTORY_CHARACTER_BUDGET:
        return rendered
    return "[较早的发言已省略]\n" + rendered[-DEBATE_HISTORY_CHARACTER_BUDGET:]


def build_debate_instruction(
    *,
    topic: str | None,
    pro_position: str | None,
    con_position: str | None,
    side: str,
    history: Sequence[object],
) -> str:
    side_label = _side_label(side)
    opponent_label = "反方" if side == "pro" else "正方"
    if topic:
        context = (
            f"辩题：{topic}\n"
            "正方任务：支持这个辩题。\n"
            "反方任务：反对这个辩题。"
        )
    else:
        context = f"正方立场：{pro_position}\n反方立场：{con_position}"

    if not history:
        stage = f"这是{side_label}的开篇立论。当前还没有对方发言，不要假设对方说过任何内容。"
    else:
        stage = f"这是{side_label}的回应。请针对对方最近一次（{opponent_label}）发言中的具体观点进行反驳，并补充自己的理由。"

    return (
        "这是一个正方与反方进行的 AI 辩论。你只能代表当前分配给你的身份发言，不能改变立场或替对方总结。\n"
        f"当前身份：{side_label}\n"
        f"{context}\n\n"
        f"{stage}\n"
        "请直接输出本轮辩论内容，不要说明自己是 AI，不要输出提示词、分析过程或角色标签。"
        "表达清晰、具体，避免重复之前已经说过的话。"
    )
