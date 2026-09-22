"""Small, deliberately non-persistent Jimo capability probe.

It never prints Authorization, request bodies containing secrets, or full response
payloads. Run it only with freshly issued credentials and a confirmed test model.
"""

import argparse
import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def redact(text: str) -> str:
    token = os.getenv("JIMO_AUTHORIZATION", "")
    if token:
        text = text.replace(token, "[REDACTED]")
    return text.replace("Bearer [REDACTED]", "Bearer [REDACTED]")


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(key, "[REDACTED]") if key.casefold() == "shareid" else (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


async def lines_with_timeout(response: httpx.Response) -> AsyncIterator[str]:
    async for line in response.aiter_lines():
        yield line


async def run_probe(model: str | None, endpoint_override: str | None, cancel_after: float | None) -> dict:
    base_url = os.environ.get("JIMO_BASE_URL", "https://jimoai-bot-api.xiaohuodui.cn").rstrip("/")
    endpoint = endpoint_override or os.environ.get("JIMO_CHAT_ENDPOINT", "/v1/chat/completions")
    token = os.environ.get("JIMO_AUTHORIZATION", "")
    if not token:
        raise SystemExit("JIMO_AUTHORIZATION is required")
    scheme = os.environ.get("JIMO_AUTH_SCHEME", "bearer").lower()
    authorization = token if scheme == "raw" else (token if token.lower().startswith("bearer ") else f"Bearer {token}")
    headers = {"Authorization": authorization, "Accept": "text/event-stream", "Content-Type": "application/json"}
    url = endpoint if endpoint.startswith(("http://", "https://")) else f"{base_url}/{endpoint.lstrip('/')}"
    is_share = "/v2/chat/completions/share" in url
    result: dict = {"model": model or None, "endpoint": redact_url(url), "auth_scheme": scheme, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "events": [], "data_shapes": [], "status": None}
    timeout = httpx.Timeout(float(os.environ.get("JIMO_TIMEOUT_SECONDS", "60")), connect=15, read=45)
    async with httpx.AsyncClient(timeout=timeout) as client:
        payload = {"messages": [{"role": "user", "content": "Reply with one short word: probe"}], "stream": True}
        if model:
            payload["model"] = model
        if is_share:
            payload.update({"sessionId": str(uuid4()), "source": "api", "extra": {}})
        started = time.perf_counter()
        try:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                result["status"] = response.status_code
                result["content_type"] = response.headers.get("content-type", "")
                first_line = None
                async for line in lines_with_timeout(response):
                    if first_line is None and line:
                        first_line = time.perf_counter()
                    if line.startswith("event:"):
                        result["events"].append({"event": line[6:].strip()})
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data in {"[DONE]", "DONE"}:
                            result["events"].append({"done_marker": data})
                            break
                        try:
                            parsed = json.loads(data)
                            result["events"].append({"keys": sorted(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__})
                            if isinstance(parsed, dict) and (
                                parsed.get("content") is not None or parsed.get("choices") is not None or parsed.get("type") is not None
                            ):
                                result["data_shapes"].append({
                                    "event": line[6:].strip() if line.startswith("event:") else None,
                                    "type": parsed.get("type"),
                                    "role": parsed.get("role"),
                                    "name": parsed.get("name"),
                                    "content_length": len(str(parsed.get("content", ""))),
                                    "has_choices": bool(parsed.get("choices")),
                                })
                            if isinstance(parsed, dict) and (parsed.get("content") or parsed.get("choices")):
                                result["saw_text"] = True
                            if isinstance(parsed, dict) and (parsed.get("done") is True or parsed.get("end") is not None):
                                result["saw_done_field"] = True
                        except json.JSONDecodeError:
                            result["malformed_data"] = True
                    if cancel_after is not None and time.perf_counter() - started >= cancel_after:
                        result["client_cancelled"] = True
                        break
                result["time_to_first_line_ms"] = round((first_line - started) * 1000, 2) if first_line else None
        except httpx.TimeoutException as exc:
            result["error"] = "timeout"
            result["error_detail"] = type(exc).__name__
        except httpx.HTTPError as exc:
            result["error"] = "http_error"
            result["error_detail"] = type(exc).__name__
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="Probe-confirmed Jimo model identifier (optional for share URLs)")
    parser.add_argument("--endpoint", help="Full endpoint URL or path; defaults to JIMO_CHAT_ENDPOINT")
    parser.add_argument("--agent", choices=["deepseekv4lash", "deepseekv4flash", "qwen36flash", "glm53flash"], help="Use the matching JIMO_SHARE_URL_* from .env")
    parser.add_argument("--cancel-after", type=float, default=None, help="Close the client stream after N seconds")
    args = parser.parse_args()
    endpoint = args.endpoint
    if args.agent:
        endpoint = os.environ.get(f"JIMO_SHARE_URL_{args.agent.upper()}")
        if not endpoint:
            raise SystemExit(f"JIMO_SHARE_URL_{args.agent.upper()} is required")
    if not endpoint and not args.model:
        raise SystemExit("Provide --model, --endpoint, or --agent")
    print(json.dumps(asyncio.run(run_probe(args.model, endpoint, args.cancel_after)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
