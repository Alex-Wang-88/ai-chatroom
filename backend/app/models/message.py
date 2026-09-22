from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, id_column


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = id_column()
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    round_id: Mapped[str | None] = mapped_column(ForeignKey("rounds.id", ondelete="SET NULL"), nullable=True)
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sender_display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    display_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_token_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation = relationship("Conversation", back_populates="messages")
    round = relationship("Round", back_populates="messages", foreign_keys=[round_id])
    generation_runs = relationship("GenerationRun", back_populates="message", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("conversation_id", "client_message_id", name="uq_messages_client_id"),
        Index("ix_messages_display", "conversation_id", "display_sequence", "created_at"),
    )
