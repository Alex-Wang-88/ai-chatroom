# Windows desktop packaging

The Tauri v2 shell lives in `src-tauri`. During development it points at the
localhost Vite server. The FastAPI sidecar entry point selects an available
`127.0.0.1` port unless `AI_CHAT_ROOM_PORT` is supplied. A production build
should first produce the PyInstaller sidecar with
`./desktop/build-backend.ps1`, then wire Tauri's sidecar process lifecycle to
the selected port and per-install app-data database path before shipping an
installer. Credentials remain outside the frontend bundle.
