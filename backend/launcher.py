"""Local sidecar entry point used by the desktop bundle."""

import os
import socket

import uvicorn


def _free_local_port() -> int:
    requested = int(os.environ.get("AI_CHAT_ROOM_PORT", "0"))
    if requested:
        return requested
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=_free_local_port(), log_level="info")
