import pytest
from app.realtime.event_hub import ConversationEventHub


@pytest.mark.asyncio
async def test_event_hub_sequences_and_replays():
    hub = ConversationEventHub(ring_size=3)
    await hub.publish("c", "one", {})
    await hub.publish("c", "two", {})
    queue, replay, gap = hub.subscribe("c", 1)
    assert not gap
    assert [item["type"] for item in replay] == ["two"]
    hub.unsubscribe("c", queue)
