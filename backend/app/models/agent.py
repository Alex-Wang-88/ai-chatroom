
from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, id_column


class Agent(Base, TimestampMixin):
    __tablename__ = "agents"

    id: Mapped[str] = id_column()
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    mention_handle: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    mention_aliases: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), default="jimo", nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    talkativeness: Mapped[float] = mapped_column(default=1.0, nullable=False)
    temperature: Mapped[float | None] = mapped_column(nullable=True)
    max_output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)

    conversation_links = relationship("ConversationAgent", back_populates="agent", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_agents_mention_handle", "mention_handle", unique=True),)


class ConversationAgent(Base):
    __tablename__ = "conversation_agents"

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True)
    muted: Mapped[bool] = mapped_column(default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)

    agent = relationship("Agent", back_populates="conversation_links")

    __table_args__ = (Index("ix_conversation_agents_routing", "conversation_id", "enabled", "muted"),)
