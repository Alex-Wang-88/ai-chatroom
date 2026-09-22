from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, id_column


class GenerationRun(Base):
    __tablename__ = "generation_runs"

    id: Mapped[str] = id_column()
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    round_id: Mapped[str] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    context_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("context_snapshots.id"), nullable=True)
    request_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_token_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_to_first_token_ms: Mapped[float | None] = mapped_column(nullable=True)
    generation_duration_ms: Mapped[float | None] = mapped_column(nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    tokens_per_second: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    message = relationship("Message", back_populates="generation_runs")
    round = relationship("Round", back_populates="generations")
    context_snapshot = relationship("ContextSnapshot", back_populates="generation_runs")

    __table_args__ = (
        UniqueConstraint("message_id", "attempt_number", name="uq_generation_attempt"),
        Index("ix_generations_round_status", "round_id", "status"),
        Index("ix_generations_agent_started", "agent_id", "request_started_at"),
    )
