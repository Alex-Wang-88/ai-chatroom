from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, id_column


class ContextSnapshot(Base):
    __tablename__ = "context_snapshots"

    id: Mapped[str] = id_column()
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    strategy: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cutoff_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    message_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    serialized_transcript: Mapped[str] = mapped_column(Text, default="", nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    rounds = relationship("Round", back_populates="context_snapshot")
    generation_runs = relationship("GenerationRun", back_populates="context_snapshot")

    __table_args__ = (Index("ix_context_snapshots_conversation_created", "conversation_id", "created_at"),)
