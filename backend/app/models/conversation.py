from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, id_column


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[str] = id_column()
    title: Mapped[str] = mapped_column(String(200), default="新建聊天", nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="topic", nullable=False)
    context_strategy: Mapped[str] = mapped_column(String(40), default="recent_messages", nullable=False)
    context_message_limit: Mapped[int] = mapped_column(default=20, nullable=False)
    context_character_budget: Mapped[int] = mapped_column(default=24000, nullable=False)
    free_max_messages: Mapped[int] = mapped_column(default=8, nullable=False)
    max_consecutive_messages: Mapped[int] = mapped_column(default=2, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    rounds = relationship("Round", back_populates="conversation", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_conversations_updated_at", "updated_at"), Index("ix_conversations_archived_at", "archived_at"))
