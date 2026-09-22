export type Mode = 'topic' | 'free'
export type MessageStatus = 'pending' | 'streaming' | 'completed' | 'error' | 'cancelled'
export type DebateInputMode = 'topic' | 'positions'
export type DebateSide = 'pro' | 'con'
export type DebateStatus = 'active' | 'ended'

export interface Conversation {
  id: string
  title: string
  mode: Mode
  context_strategy: string
  context_message_limit: number
  context_character_budget: number
  free_max_messages: number
  max_consecutive_messages: number
  created_at: string
  updated_at: string
  archived_at: string | null
}

export interface Agent {
  id: string
  display_name: string
  mention_handle: string
  mention_aliases: string[]
  avatar: string | null
  provider: string
  model_id: string
  system_prompt: string
  talkativeness: number
  temperature: number | null
  max_output_tokens: number | null
  enabled: boolean
}

export interface ConversationAgent {
  agent: Agent
  muted: boolean
  enabled: boolean
  sort_order: number
}

export interface Message {
  id: string
  conversation_id: string
  round_id: string | null
  sender_type: 'user' | 'agent'
  sender_id: string | null
  sender_display_name: string
  content: string
  status: MessageStatus
  display_sequence: number | null
  created_at: string
  first_token_at: string | null
  finished_at: string | null
}

export interface Round {
  id: string
  conversation_id: string
  round_number: number
  mode: Mode
  status: string
  trigger_message_id: string | null
  context_snapshot_id: string | null
  started_at: string | null
  finished_at: string | null
  stop_reason: string | null
  completed_count: number
  error_count: number
  cancelled_count: number
}

export interface EventEnvelope {
  protocol_version: number
  type: string
  stream_epoch: string
  sequence: number
  occurred_at: string
  conversation_id: string
  payload: Record<string, unknown>
}

export interface DebateTurn {
  side: DebateSide
  content: string
  agent_id: string
  display_name: string
  model_id: string
}

export interface DebateResponseRequest {
  debate_id: string
  topic: string | null
  pro_position: string | null
  con_position: string | null
  pro_agent_id: string
  con_agent_id: string
  side: DebateSide
  history: Array<Pick<DebateTurn, 'side' | 'content'>>
}

export interface DebateCreateRequest {
  title?: string | null
  topic: string | null
  pro_position: string | null
  con_position: string | null
  pro_agent_id: string
  con_agent_id: string
}

export interface DebateResponse {
  side: DebateSide
  content: string
  agent_id: string
  display_name: string
  model_id: string
}

export interface DebateSummary {
  id: string
  title: string
  topic: string | null
  pro_position: string | null
  con_position: string | null
  pro_agent_id: string
  con_agent_id: string
  status: DebateStatus
  turn_count: number
  created_at: string
  updated_at: string
  ended_at: string | null
}

export interface DebateRecord extends DebateSummary {
  turns: DebateTurn[]
}
