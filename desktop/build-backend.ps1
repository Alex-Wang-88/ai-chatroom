$ErrorActionPreference = "Stop"

# Build the FastAPI sidecar after the application has a production launcher.
# Keeping this step explicit prevents developer credentials or .env files from
# being copied into the desktop bundle.
python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name AIChatRoomBackend `
  --distpath desktop/src-tauri/sidecar `
  --workpath desktop/src-tauri/build `
  --specpath desktop/src-tauri `
  --paths backend `
  backend/launcher.py
