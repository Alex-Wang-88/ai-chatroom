from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, id_column


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[str] = id_column()
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    context_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("context_snapshots.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="round_created", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    completed_count: Mapped[int] = mapped_column(default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(default=0, nullable=False)
    cancelled_count: Mapped[int] = mapped_column(default=0, nullable=False)

    conversation = relationship("Conversation", back_populates="rounds")
    messages = relationship("Message", back_populates="round", foreign_keys="Message.round_id")
    generations = relationship("GenerationRun", back_populates="round", cascade="all, delete-orphan")
    context_snapshot = relationship("ContextSnapshot", back_populates="rounds")

    __table_args__ = (
        UniqueConstraint("conversation_id", "round_number", name="uq_round_number"),
        Index("ix_rounds_conversation_status", "conversation_id", "status"),
    )
