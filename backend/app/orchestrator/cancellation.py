import asyncio


class CancellationRegistry:
    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}

    def create(self, run_id: str) -> asyncio.Event:
        event = asyncio.Event()
        self._events[run_id] = event
        return event

    def event_for(self, run_id: str) -> asyncio.Event:
        """Return the run event, failing closed if a task was misconfigured."""
        event = self._events.get(run_id)
        if event is None:
            raise KeyError(f"Cancellation event is not registered: {run_id}")
        return event

    def cancel(self, run_id: str) -> bool:
        event = self._events.get(run_id)
        if not event:
            return False
        event.set()
        return True

    def remove(self, run_id: str) -> None:
        self._events.pop(run_id, None)

    def cancel_all(self, run_ids: list[str]) -> None:
        for run_id in run_ids:
            self.cancel(run_id)
