"""Initial AI Chat Room schema."""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("conversations", sa.Column("id", sa.String(36), primary_key=True), sa.Column("title", sa.String(200), nullable=False), sa.Column("mode", sa.String(20), nullable=False), sa.Column("context_strategy", sa.String(40), nullable=False), sa.Column("context_message_limit", sa.Integer(), nullable=False), sa.Column("context_character_budget", sa.Integer(), nullable=False), sa.Column("free_max_messages", sa.Integer(), nullable=False), sa.Column("max_consecutive_messages", sa.Integer(), nullable=False), sa.Column("archived_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_conversations_updated_at", "conversations", ["updated_at"])
    op.create_index("ix_conversations_archived_at", "conversations", ["archived_at"])
    op.create_table("agents", sa.Column("id", sa.String(36), primary_key=True), sa.Column("display_name", sa.String(100), nullable=False), sa.Column("mention_handle", sa.String(100), nullable=False, unique=True), sa.Column("mention_aliases", sa.JSON(), nullable=False), sa.Column("avatar", sa.String(500)), sa.Column("provider", sa.String(50), nullable=False), sa.Column("model_id", sa.String(200), nullable=False), sa.Column("system_prompt", sa.Text(), nullable=False), sa.Column("talkativeness", sa.Float(), nullable=False), sa.Column("temperature", sa.Float()), sa.Column("max_output_tokens", sa.Integer()), sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_agents_mention_handle", "agents", ["mention_handle"], unique=True)
    op.create_table("context_snapshots", sa.Column("id", sa.String(36), primary_key=True), sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False), sa.Column("strategy", sa.String(40), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("cutoff_message_id", sa.String(36)), sa.Column("message_ids", sa.JSON(), nullable=False), sa.Column("serialized_transcript", sa.Text(), nullable=False), sa.Column("character_count", sa.Integer(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_context_snapshots_conversation_created", "context_snapshots", ["conversation_id", "created_at"])
    op.create_table("conversation_agents", sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True), sa.Column("agent_id", sa.String(36), sa.ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True), sa.Column("muted", sa.Boolean(), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("sort_order", sa.Integer(), nullable=False))
    op.create_index("ix_conversation_agents_routing", "conversation_agents", ["conversation_id", "enabled", "muted"])
    op.create_table("rounds", sa.Column("id", sa.String(36), primary_key=True), sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False), sa.Column("round_number", sa.Integer(), nullable=False), sa.Column("mode", sa.String(20), nullable=False), sa.Column("trigger_message_id", sa.String(36)), sa.Column("context_snapshot_id", sa.String(36), sa.ForeignKey("context_snapshots.id")), sa.Column("status", sa.String(30), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)), sa.Column("stop_reason", sa.String(50)), sa.Column("completed_count", sa.Integer(), nullable=False), sa.Column("error_count", sa.Integer(), nullable=False), sa.Column("cancelled_count", sa.Integer(), nullable=False), sa.UniqueConstraint("conversation_id", "round_number", name="uq_round_number"))
    op.create_index("ix_rounds_conversation_status", "rounds", ["conversation_id", "status"])
    op.create_table("messages", sa.Column("id", sa.String(36), primary_key=True), sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False), sa.Column("round_id", sa.String(36), sa.ForeignKey("rounds.id", ondelete="SET NULL")), sa.Column("sender_type", sa.String(20), nullable=False), sa.Column("sender_id", sa.String(36)), sa.Column("sender_display_name", sa.String(100), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("display_sequence", sa.Integer()), sa.Column("client_message_id", sa.String(100)), sa.Column("retry_count", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("first_token_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("conversation_id", "client_message_id", name="uq_messages_client_id"))
    op.create_index("ix_messages_display", "messages", ["conversation_id", "display_sequence", "created_at"])
    op.create_table("generation_runs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False), sa.Column("round_id", sa.String(36), sa.ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False), sa.Column("message_id", sa.String(36), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False), sa.Column("agent_id", sa.String(36), sa.ForeignKey("agents.id"), nullable=False), sa.Column("provider", sa.String(50), nullable=False), sa.Column("model_id", sa.String(200), nullable=False), sa.Column("attempt_number", sa.Integer(), nullable=False), sa.Column("context_snapshot_id", sa.String(36), sa.ForeignKey("context_snapshots.id")), sa.Column("request_started_at", sa.DateTime(timezone=True)), sa.Column("first_token_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)), sa.Column("time_to_first_token_ms", sa.Float()), sa.Column("generation_duration_ms", sa.Float()), sa.Column("input_tokens", sa.Integer()), sa.Column("output_tokens", sa.Integer()), sa.Column("tokens_per_second", sa.Float()), sa.Column("status", sa.String(20), nullable=False), sa.Column("error_type", sa.String(80)), sa.Column("error_message", sa.Text()), sa.Column("provider_request_id", sa.String(200)))
    op.create_index("ix_generations_round_status", "generation_runs", ["round_id", "status"])
    op.create_index("ix_generations_agent_started", "generation_runs", ["agent_id", "request_started_at"])
    op.create_index("uq_generation_attempt", "generation_runs", ["message_id", "attempt_number"], unique=True)


def downgrade() -> None:
    op.drop_table("generation_runs")
    op.drop_table("messages")
    op.drop_table("rounds")
    op.drop_table("conversation_agents")
    op.drop_table("context_snapshots")
    op.drop_table("agents")
    op.drop_table("conversations")
