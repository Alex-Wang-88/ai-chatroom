from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    mention_handle: str
    mention_aliases: list[str]
    avatar: str | None
    provider: str
    model_id: str
    system_prompt: str
    talkativeness: float
    temperature: float | None
    max_output_tokens: int | None
    enabled: bool


class ConversationAgentRead(BaseModel):
    agent: AgentRead
    muted: bool
    enabled: bool
    sort_order: int


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    round_id: str | None
    sender_type: Literal["user", "agent"]
    sender_id: str | None
    sender_display_name: str
    content: str
    status: str
    display_sequence: int | None
    created_at: datetime
    first_token_at: datetime | None
    finished_at: datetime | None


class GenerationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    message_id: str
    agent_id: str
    provider: str
    model_id: str
    attempt_number: int
    status: str
    request_started_at: datetime | None
    first_token_at: datetime | None
    finished_at: datetime | None
    time_to_first_token_ms: float | None
    generation_duration_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    tokens_per_second: float | None
    error_type: str | None
    error_message: str | None


class RoundRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    round_number: int
    mode: str
    status: str
    trigger_message_id: str | None
    context_snapshot_id: str | None
    started_at: datetime | None
    finished_at: datetime | None
    stop_reason: str | None
    completed_count: int
    error_count: int
    cancelled_count: int


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    mode: str
    context_strategy: str
    context_message_limit: int
    context_character_budget: int
    free_max_messages: int
    max_consecutive_messages: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class DebateTurnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    debate_id: str
    turn_number: int
    side: Literal["pro", "con"]
    content: str
    agent_id: str
    display_name: str
    model_id: str
    created_at: datetime


class DebateSummaryRead(BaseModel):
    id: str
    title: str
    topic: str | None
    pro_position: str | None
    con_position: str | None
    pro_agent_id: str
    con_agent_id: str
    status: Literal["active", "ended"]
    turn_count: int
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None


class DebateRead(DebateSummaryRead):
    turns: list[DebateTurnRead]


class ActiveRunRead(BaseModel):
    round: RoundRead | None
    messages: list[MessageRead]
    agent_states: dict[str, dict[str, Any]]


class DebateResponseRead(BaseModel):
    side: Literal["pro", "con"]
    content: str
    agent_id: str
    display_name: str
    model_id: str
