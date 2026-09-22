# ADR 0002: WebSocket Multiplexing

Decision: use one WebSocket per conversation for backend-to-browser events. Provider connections remain independent HTTP/SSE streams. REST owns commands because it gives clear idempotency and HTTP errors; WebSocket carries progress and streaming events.
