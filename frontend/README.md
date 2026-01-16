# Geo Cortex Assistant UI (Frontend)

Custom web frontend (React + Vite + TypeScript) for the Geo Cortex agent backend.

## Run (Windows / PowerShell)

1) Create runtime config:

```powershell
Copy-Item .\public\config.example.json .\public\config.json
notepad .\public\config.json
```

Tip: set `"backendUrl": ""` to use same-origin (recommended when the FastAPI backend serves the built frontend).

2) Install + start:

```powershell
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

## Documentation

See `FRONTEND_FILE_BY_FILE.md` for a **file-by-file** explanation (map, layers, table, chat, API integration, and how to extend).

See `TECHNICAL_DOCUMENTATION.md` for the **technical documentation** with architecture charts/diagrams and implementation details.
