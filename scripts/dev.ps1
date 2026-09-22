$ErrorActionPreference = 'Stop'
Start-Process -WindowStyle Hidden -FilePath 'python' -ArgumentList '-m','uvicorn','app.main:app','--reload','--app-dir','backend'
npm run dev --prefix frontend
