from dataclasses import dataclass

from app.orchestrator.mention_parser import MentionResult


@dataclass(slots=True, frozen=True)
class RoutingResult:
    selected: list[object]
    muted: list[object]
    unknown: list[str]


def route_topic(mention_result: MentionResult, links: list[object]) -> RoutingResult:
    by_handle = {link.agent.mention_handle: link for link in links if link.enabled and link.agent.enabled}
    if mention_result.handles:
        candidates = [by_handle[handle] for handle in mention_result.handles if handle in by_handle]
    else:
        candidates = list(by_handle.values())
    muted = [link.agent for link in candidates if link.muted]
    selected = [link.agent for link in candidates if not link.muted]
    return RoutingResult(selected=selected, muted=muted, unknown=mention_result.unknown)


def route_free_priority(mention_result: MentionResult, links: list[object]) -> tuple[list[object], list[object]]:
    by_handle = {link.agent.mention_handle: link for link in links if link.enabled and link.agent.enabled}
    priority: list[object] = []
    muted: list[object] = []
    for handle in mention_result.handles:
        link = by_handle.get(handle)
        if not link:
            continue
        if link.muted:
            muted.append(link.agent)
        elif link.agent not in priority:
            priority.append(link.agent)
    return priority, muted
