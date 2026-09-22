from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, id_column, utc_now


class Debate(Base, TimestampMixin):
    __tablename__ = "debates"

    id: Mapped[str] = id_column()
    title: Mapped[str] = mapped_column(String(200), default="新建辩论", nullable=False)
    topic: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pro_position: Mapped[str | None] = mapped_column(Text, nullable=True)
    con_position: Mapped[str | None] = mapped_column(Text, nullable=True)
    pro_agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    con_agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    turns = relationship(
        "DebateTurn",
        back_populates="debate",
        cascade="all, delete-orphan",
        order_by="DebateTurn.turn_number",
    )

    __table_args__ = (Index("ix_debates_updated_at", "updated_at"), Index("ix_debates_status", "status"))


class DebateTurn(Base):
    __tablename__ = "debate_turns"

    id: Mapped[str] = id_column()
    debate_id: Mapped[str] = mapped_column(ForeignKey("debates.id", ondelete="CASCADE"), nullable=False)
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    debate = relationship("Debate", back_populates="turns")

    __table_args__ = (
        UniqueConstraint("debate_id", "turn_number", name="uq_debate_turn_number"),
        Index("ix_debate_turns_debate", "debate_id", "turn_number"),
    )
