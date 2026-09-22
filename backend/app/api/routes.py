import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Agent
from app.orchestrator.service import ConversationOrchestrator, OrchestratorError
from app.schemas.commands import (
    AgentSettingsUpdate,
    AgentUpdate,
    ConversationCreate,
    ConversationUpdate,
    DebateCreate,
    DebateResponseCreate,
    DebateUpdate,
    MessageCreate,
    NextRoundCreate,
)
from app.schemas.entities import (
    AgentRead,
    ConversationAgentRead,
    ConversationRead,
    DebateRead,
    DebateResponseRead,
    DebateSummaryRead,
    DebateTurnRead,
    GenerationRead,
    MessageRead,
    RoundRead,
)
from app.schemas.events import event_payload

router = APIRouter(prefix="/api/v1")


def get_orchestrator() -> ConversationOrchestrator:
    from app.main import orchestrator

    return orchestrator


def _raise(exc: OrchestratorError) -> None:
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)})


def _debate_summary(debate) -> DebateSummaryRead:
    return DebateSummaryRead(
        id=debate.id,
        title=debate.title,
        topic=debate.topic,
        pro_position=debate.pro_position,
        con_position=debate.con_position,
        pro_agent_id=debate.pro_agent_id,
        con_agent_id=debate.con_agent_id,
        status=debate.status,
        turn_count=len(debate.turns),
        created_at=debate.created_at,
        updated_at=debate.updated_at,
        ended_at=debate.ended_at,
    )


def _debate_read(debate) -> DebateRead:
    summary = _debate_summary(debate)
    return DebateRead(
        **summary.model_dump(),
        turns=[DebateTurnRead.model_validate(turn) for turn in debate.turns],
    )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/conversations", response_model=ConversationRead, status_code=201)
async def create_conversation(payload: ConversationCreate, service: ConversationOrchestrator = Depends(get_orchestrator)):
    return await service.create_conversation(payload.title, payload.mode)


@router.get("/conversations", response_model=list[ConversationRead])
async def list_conversations(limit: int = Query(50, ge=1, le=200), service: ConversationOrchestrator = Depends(get_orchestrator)):
    return await service.list_conversations(limit)


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
async def get_conversation(conversation_id: str, service: ConversationOrchestrator = Depends(get_orchestrator)):
    conversation = await service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Conversation not found"})
    return conversation


@router.patch("/conversations/{conversation_id}", response_model=ConversationRead)
async def update_conversation(conversation_id: str, payload: ConversationUpdate, service: ConversationOrchestrator = Depends(get_orchestrator)):
    try:
        return await service.update_conversation(conversation_id, payload.model_dump(exclude_unset=True))
    except OrchestratorError as exc:
        _raise(exc)


@router.post("/conversations/{conversation_id}/archive", response_model=ConversationRead)
async def archive_conversation(conversation_id: str, service: ConversationOrchestrator = Depends(get_orchestrator)):
    try:
        return await service.archive_conversation(conversation_id)
    except OrchestratorError as exc:
        _raise(exc)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageRead])
async def get_messages(
    conversation_id: str,
    limit: int = Query(100, ge=1, le=500),
    before: datetime | None = None,
    service: ConversationOrchestrator = Depends(get_orchestrator),
):
    return await service.get_messages(conversation_id, limit, before)


@router.post("/conversations/{conversation_id}/messages", response_model=dict, status_code=202)
async def submit_message(conversation_id: str, payload: MessageCreate, service: ConversationOrchestrator = Depends(get_orchestrator)):
    try:
        message, round_row = await service.submit_message(conversation_id, payload.content, payload.client_message_id)
        return {"message": MessageRead.model_validate(message), "round": RoundRead.model_validate(round_row)}
    except OrchestratorError as exc:
        _raise(exc)


@router.post("/debates/respond", response_model=DebateResponseRead)
async def debate_response(payload: DebateResponseCreate, service: ConversationOrchestrator = Depends(get_orchestrator)):
    try:
        content, agent = await service.generate_debate_response(
            debate_id=payload.debate_id,
            topic=payload.topic,
            pro_position=payload.pro_position,
            con_position=payload.con_position,
            pro_agent_id=payload.pro_agent_id,
            con_agent_id=payload.con_agent_id,
            side=payload.side,
            history=[turn.model_dump() for turn in payload.history],
            persist=True,
        )
        return DebateResponseRead(
            side=payload.side,
            content=content,
            agent_id=agent.id,
            display_name=agent.display_name,
            model_id=agent.model_id,
        )
    except OrchestratorError as exc:
        _raise(exc)


@router.post("/debates/respond/stream")
async def debate_response_stream(payload: DebateResponseCreate, service: ConversationOrchestrator = Depends(get_orchestrator)):
    async def events():
        async for event in service.stream_debate_response(
            debate_id=payload.debate_id,
            topic=payload.topic,
            pro_position=payload.pro_position,
            con_position=payload.con_position,
            pro_agent_id=payload.pro_agent_id,
            con_agent_id=payload.con_agent_id,
            side=payload.side,
            history=[turn.model_dump() for turn in payload.history],
            persist=True,
        ):
            event_name = str(event.get("event", "message"))
            data = {key: value for key, value in event.items() if key != "event"}
            yield f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/debates", response_model=DebateRead, status_code=201)
async def create_debate(payload: DebateCreate, service: ConversationOrchestrator = Depends(get_orchestrator)):
    try:
        debate = await service.create_debate(
            title=payload.title,
            topic=payload.topic,
            pro_position=payload.pro_position,
            con_position=payload.con_position,
            pro_agent_id=payload.pro_agent_id,
            con_agent_id=payload.con_agent_id,
        )
        return _debate_read(debate)
    except OrchestratorError as exc:
        _raise(exc)


@router.get("/debates", response_model=list[DebateSummaryRead])
async def list_debates(limit: int = Query(50, ge=1, le=200), service: ConversationOrchestrator = Depends(get_orchestrator)):
    return [_debate_summary(debate) for debate in await service.list_debates(limit)]


@router.get("/debates/{debate_id}", response_model=DebateRead)
async def get_debate(debate_id: str, service: ConversationOrchestrator = Depends(get_orchestrator)):
    debate = await service.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Debate not found"})
    return _debate_read(debate)


@router.patch("/debates/{debate_id}", response_model=DebateSummaryRead)
async def rename_debate(debate_id: str, payload: DebateUpdate, service: ConversationOrchestrator = Depends(get_orchestrator)):
    try:
        return _debate_summary(await service.rename_debate(debate_id, payload.title))
    except OrchestratorError as exc:
        _raise(exc)


@router.post("/debates/{debate_id}/end", response_model=DebateSummaryRead)
async def end_debate(debate_id: str, service: ConversationOrchestrator = Depends(get_orchestrator)):
    try:
        return _debate_summary(await service.end_debate(debate_id))
    except OrchestratorError as exc:
        _raise(exc)


@router.post("/conversations/{conversation_id}/rounds/next", response_model=RoundRead, status_code=202)
async def next_round(conversation_id: str, _: NextRoundCreate, service: ConversationOrchestrator = Depends(get_orchestrator)):
    try:
        return await service.next_round(conversation_id, _.idempotency_key)
    except OrchestratorError as exc:
        _raise(exc)


@router.get("/conversations/{conversation_id}/agents", response_model=list[ConversationAgentRead])
async def conversation_agents(conversation_id: str, service: ConversationOrchestrator = Depends(get_orchestrator)):
    links = await service.conversation_agents(conversation_id)
    return [ConversationAgentRead(agent=AgentRead.model_validate(link.agent), muted=link.muted, enabled=link.enabled, sort_order=link.sort_order) for link in links]


@router.patch("/conversations/{conversation_id}/agents/{agent_id}", response_model=ConversationAgentRead)
async def update_conversation_agent(conversation_id: str, agent_id: str, payload: AgentSettingsUpdate, service: ConversationOrchestrator = Depends(get_orchestrator)):
    try:
        link = await service.update_agent_settings(conversation_id, agent_id, payload.model_dump(exclude_unset=True))
        return ConversationAgentRead(agent=AgentRead.model_validate(link.agent), muted=link.muted, enabled=link.enabled, sort_order=link.sort_order)
    except OrchestratorError as exc:
        _raise(exc)


@router.get("/agents", response_model=list[AgentRead])
async def list_agents(session: AsyncSession = Depends(get_session)):
    return list((await session.execute(select(Agent).order_by(Agent.display_name))).scalars().all())


@router.patch("/agents/{agent_id}", response_model=AgentRead)
async def update_agent(agent_id: str, payload: AgentUpdate, service: ConversationOrchestrator = Depends(get_orchestrator)):
    try:
        return await service.update_agent(agent_id, payload.model_dump(exclude_unset=True))
    except OrchestratorError as exc:
        _raise(exc)


@router.post("/rounds/{round_id}/cancel", status_code=202)
async def cancel_round(round_id: str, service: ConversationOrchestrator = Depends(get_orchestrator)):
    try:
        await service.cancel_round(round_id)
        return {"status": "cancellation_requested", "round_id": round_id}
    except OrchestratorError as exc:
        _raise(exc)


@router.post("/conversations/{conversation_id}/free-mode/stop", status_code=202)
async def stop_free_mode(conversation_id: str, service: ConversationOrchestrator = Depends(get_orchestrator)):
    state = await service.active_state(conversation_id)
    round_row = state["round"]
    if not round_row or round_row.mode != "free":
        raise HTTPException(status_code=409, detail={"code": "free_mode_not_active", "message": "Free mode is not active"})
    try:
        await service.cancel_round(round_row.id)
        return {"status": "cancellation_requested", "round_id": round_row.id}
    except OrchestratorError as exc:
        _raise(exc)


@router.post("/generation-runs/{run_id}/cancel", status_code=202)
async def cancel_generation(run_id: str, service: ConversationOrchestrator = Depends(get_orchestrator)):
    if not await service.cancel_generation(run_id):
        raise HTTPException(status_code=404, detail={"code": "run_not_active", "message": "Generation is not active"})
    return {"status": "cancellation_requested", "run_id": run_id}


@router.post("/messages/{message_id}/retry", response_model=GenerationRead, status_code=202)
async def retry_message(message_id: str, service: ConversationOrchestrator = Depends(get_orchestrator)):
    try:
        run = await service.retry_message(message_id)
        return run
    except OrchestratorError as exc:
        _raise(exc)


@router.get("/conversations/{conversation_id}/active-run")
async def active_run(conversation_id: str, service: ConversationOrchestrator = Depends(get_orchestrator)):
    state = await service.active_state(conversation_id)
    return {
        "round": RoundRead.model_validate(state["round"]).model_dump(mode="json") if state["round"] else None,
        "messages": [MessageRead.model_validate(message).model_dump(mode="json") for message in state["messages"]],
        "agent_states": state["agent_states"],
    }


@router.websocket("/ws/v1/conversations/{conversation_id}")
async def conversation_socket(websocket: WebSocket, conversation_id: str, after_sequence: int = 0):
    service = get_orchestrator()
    if not await service.get_conversation(conversation_id):
        await websocket.close(code=1008, reason="Conversation not found")
        return
    await websocket.accept()
    await websocket.send_json(event_payload("connection.ready", conversation_id, {"stream_epoch": service.hub.epoch}, service.hub.epoch, 0))
    queue, replay, gap = service.hub.subscribe(conversation_id, after_sequence)
    try:
        if gap:
            await websocket.send_json(event_payload("sync.required", conversation_id, {"reason": "event_gap"}, service.hub.epoch, service.hub._sequence[conversation_id]))
        for event in replay:
            await websocket.send_json(event)
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        service.hub.unsubscribe(conversation_id, queue)
