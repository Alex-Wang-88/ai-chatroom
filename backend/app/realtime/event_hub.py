import asyncio
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from uuid import uuid4


class ConversationEventHub:
    def __init__(self, ring_size: int = 1000) -> None:
        self.epoch = str(uuid4())
        self.ring_size = ring_size
        self._sequence: dict[str, int] = defaultdict(int)
        self._rings: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=ring_size))
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    async def publish(self, conversation_id: str, event_type: str, payload: dict) -> dict:
        from app.schemas.events import event_payload

        self._sequence[conversation_id] += 1
        event = event_payload(event_type, conversation_id, payload, self.epoch, self._sequence[conversation_id])
        self._rings[conversation_id].append(event)
        for queue in tuple(self._subscribers[conversation_id]):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except asyncio.QueueEmpty:
                    pass
        return event

    def subscribe(self, conversation_id: str, after_sequence: int = 0) -> tuple[asyncio.Queue, list[dict], bool]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers[conversation_id].add(queue)
        ring = list(self._rings[conversation_id])
        replay = [event for event in ring if event["sequence"] > after_sequence]
        gap = bool(replay and replay[0]["sequence"] > after_sequence + 1)
        if after_sequence and not replay and self._sequence[conversation_id] > after_sequence:
            gap = True
        return queue, replay, gap

    def unsubscribe(self, conversation_id: str, queue: asyncio.Queue) -> None:
        self._subscribers[conversation_id].discard(queue)

    async def events(self, conversation_id: str, after_sequence: int = 0) -> AsyncIterator[dict]:
        queue, replay, gap = self.subscribe(conversation_id, after_sequence)
        try:
            if gap:
                yield await self.publish(conversation_id, "sync.required", {"reason": "event_gap"})
            for event in replay:
                yield event
            while True:
                yield await queue.get()
        finally:
            self.unsubscribe(conversation_id, queue)
