from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    mode: Literal["topic", "free"] = "topic"


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    mode: Literal["topic", "free"] | None = None
    context_message_limit: int | None = Field(default=None, ge=1, le=200)
    context_character_budget: int | None = Field(default=None, ge=1000, le=200000)
    free_max_messages: int | None = Field(default=None, ge=1, le=1000)
    max_consecutive_messages: int | None = Field(default=None, ge=1, le=20)


class DebateCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    topic: str | None = Field(default=None, max_length=200)
    pro_position: str | None = Field(default=None, max_length=1000)
    con_position: str | None = Field(default=None, max_length=1000)
    pro_agent_id: str = Field(min_length=1, max_length=36)
    con_agent_id: str = Field(min_length=1, max_length=36)

    @model_validator(mode="after")
    def validate_setup(self) -> "DebateCreate":
        self.title = self.title.strip() if self.title else None
        self.topic = self.topic.strip() if self.topic else None
        self.pro_position = self.pro_position.strip() if self.pro_position else None
        self.con_position = self.con_position.strip() if self.con_position else None

        has_topic = bool(self.topic)
        has_any_position = bool(self.pro_position or self.con_position)
        has_both_positions = bool(self.pro_position and self.con_position)
        if has_topic and has_any_position:
            raise ValueError("Provide either a topic or both positions, not both")
        if not has_topic and not has_both_positions:
            raise ValueError("Provide a topic or both pro and con positions")
        return self


class DebateUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def normalize_title(self) -> "DebateUpdate":
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("Debate title cannot be blank")
        return self


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=100000)
    client_message_id: str | None = Field(default=None, max_length=100)


class NextRoundCreate(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=100)


class DebateTurnCreate(BaseModel):
    side: Literal["pro", "con"]
    content: str = Field(min_length=1)

    @model_validator(mode="after")
    def normalize_content(self) -> "DebateTurnCreate":
        self.content = self.content.strip()
        if not self.content:
            raise ValueError("Debate turn content cannot be blank")
        return self


class DebateResponseCreate(BaseModel):
    debate_id: str = Field(min_length=1, max_length=100)
    topic: str | None = Field(default=None, max_length=200)
    pro_position: str | None = Field(default=None, max_length=1000)
    con_position: str | None = Field(default=None, max_length=1000)
    pro_agent_id: str = Field(min_length=1, max_length=36)
    con_agent_id: str = Field(min_length=1, max_length=36)
    side: Literal["pro", "con"]
    history: list[DebateTurnCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_setup_and_turn(self) -> "DebateResponseCreate":
        self.debate_id = self.debate_id.strip()
        self.topic = self.topic.strip() if self.topic else None
        self.pro_position = self.pro_position.strip() if self.pro_position else None
        self.con_position = self.con_position.strip() if self.con_position else None

        has_topic = bool(self.topic)
        has_any_position = bool(self.pro_position or self.con_position)
        has_both_positions = bool(self.pro_position and self.con_position)
        if has_topic and has_any_position:
            raise ValueError("Provide either a topic or both positions, not both")
        if not has_topic and not has_both_positions:
            raise ValueError("Provide a topic or both pro and con positions")

        expected_sides = ["pro" if index % 2 == 0 else "con" for index in range(len(self.history) + 1)]
        if any(turn.side != expected_sides[index] for index, turn in enumerate(self.history)):
            raise ValueError("Debate history must alternate pro and con")
        if self.side != expected_sides[-1]:
            raise ValueError(f"The next debate side must be {expected_sides[-1]}")
        return self


class AgentSettingsUpdate(BaseModel):
    muted: bool | None = None
    enabled: bool | None = None
    sort_order: int | None = None


class AgentUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    mention_handle: str | None = Field(default=None, max_length=100)
    mention_aliases: list[str] | None = None
    avatar: str | None = Field(default=None, max_length=500)
    system_prompt: str | None = None
    talkativeness: float | None = Field(default=None, ge=0, le=10)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, ge=1, le=100000)
    enabled: bool | None = None
