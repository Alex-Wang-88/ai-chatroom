import re
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class MentionResult:
    handles: list[str]
    unknown: list[str]


_MENTION_RE = re.compile(r"(?<!\w)@([\w\u3400-\u9fff.-]+)", re.UNICODE)


def parse_mentions(content: str, agents: list[object]) -> MentionResult:
    lookup: dict[str, str] = {}
    for agent in agents:
        handle = str(agent.mention_handle).casefold()
        lookup[handle] = str(agent.mention_handle)
        for alias in agent.mention_aliases or []:
            lookup[str(alias).casefold()] = str(agent.mention_handle)
        lookup[str(agent.display_name).casefold()] = str(agent.mention_handle)

    handles: list[str] = []
    unknown: list[str] = []
    for match in _MENTION_RE.finditer(content):
        token = match.group(1)
        canonical = lookup.get(token.casefold())
        if canonical and canonical not in handles:
            handles.append(canonical)
        elif not canonical and token not in unknown:
            unknown.append(token)
    return MentionResult(handles=handles, unknown=unknown)
