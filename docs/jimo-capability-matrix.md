# Jimo Capability Matrix

This matrix records only redacted observations. Share identifiers and
authorization values never belong in this file, logs, fixtures, or frontend
bundles.

## 2026-09-01 configuration note

The three configured `/v2/chat/completions/share` endpoints were probed with a
short Chinese prompt using the locally configured raw `Authorization` value.
All three returned HTTP 200 with `Content-Type: text/event-stream` and emitted
visible text. The share URL selects the agent, so no ordinary `/v1` model ID was
needed or confirmed by this probe.

| Agent | Request shape | Observed stream | Termination | Usage/model ID |
| --- | --- | --- | --- | --- |
| `deepseekv4lash` | `POST` share URL, `messages`, `stream=true`, `sessionId`, `source=api`, raw auth | `event:data` answer payloads (`type=data`, `role=assistant`, `content`) plus workflow `event` payloads | `event:end`/`end`; parser also supports `[DONE]` | No usage or model ID confirmed |
| `qwen36flash` | same | same; workflow events are separate from answer content | `event:end`/`end` | No usage or model ID confirmed |
| `glm53flash` | same | answer `type=data` mixed with `type=thinking`; thinking is internal and must not be shown | Probe was client-cancelled after the short observation window; upstream billing stop is unknown | No usage or model ID confirmed |

The provider now ignores workflow events and custom `type=thinking` (including
reasoning/analysis aliases), while preserving normal OpenAI-compatible
`choices[].delta.content` and custom `type=data` answer chunks. This prevents
GLM's internal English reasoning from being persisted as a chat message.

Each room member now receives a deterministic UUID derived from the local
conversation and Agent IDs. The room ID is deliberately not reused across
agents, because doing so can merge provider-side histories under one share
agent even when the three share URLs are different.

Cancellation was verified only from the client side: the local parser stops
reading and closes the HTTP stream. The service makes no claim that this stops
upstream generation or billing until Jimo documents or confirms that behavior.

To repeat the redacted probe:

```powershell
python scripts/probe_jimo.py --agent deepseekv4flash
python scripts/probe_jimo.py --agent qwen36flash
python scripts/probe_jimo.py --agent glm53flash
```
