# WebSocket Protocol

Every event is an envelope with `protocol_version`, `type`, `stream_epoch`, `sequence`, `occurred_at`, `conversation_id`, and `payload`. Delta events are ephemeral and idempotent by `(stream_epoch, sequence, message_id, delta_index)`; when the client detects a gap it requests a snapshot over REST.
