import random
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(slots=True)
class SpeakerStat:
    messages: int = 0
    messages_since_last: int = 0
    consecutive: int = 0
    failed: bool = False


class FreeScheduler:
    def __init__(self, *, max_consecutive: int = 2, rng: random.Random | None = None) -> None:
        self.max_consecutive = max_consecutive
        self.rng = rng or random.Random()

    def choose(self, agents: Iterable[object], stats: dict[str, SpeakerStat], excluded_ids: Iterable[str] = ()) -> object | None:
        excluded = set(excluded_ids)
        candidates = []
        weights = []
        for agent in agents:
            if agent.id in excluded:
                continue
            stat = stats.setdefault(agent.id, SpeakerStat())
            if stat.failed or stat.consecutive >= self.max_consecutive:
                continue
            base = max(0.0, float(agent.talkativeness or 0.0))
            if base <= 0:
                continue
            recency_boost = 1.0 + min(stat.messages_since_last, 10) * 0.15
            recent_penalty = 0.25 if stat.consecutive else 1.0
            candidates.append(agent)
            weights.append(base * recency_boost * recent_penalty * self.rng.uniform(0.85, 1.15))
        if not candidates or sum(weights) <= 0:
            return None
        return self.rng.choices(candidates, weights=weights, k=1)[0]

    @staticmethod
    def record_speaker(stats: dict[str, SpeakerStat], agent_id: str, all_agent_ids: Iterable[str]) -> None:
        for current_id in all_agent_ids:
            stat = stats.setdefault(current_id, SpeakerStat())
            stat.messages_since_last = 0 if current_id == agent_id else stat.messages_since_last + 1
            if current_id == agent_id:
                stat.messages += 1
                stat.consecutive += 1
            else:
                stat.consecutive = 0
