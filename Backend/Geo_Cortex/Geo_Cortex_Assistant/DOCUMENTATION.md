# Geo_Cortex_Assistant — Backend Documentation

This document summarizes **all implemented backend work** and the **system features** for the Geo_Cortex_Assistant capstone.

## Contents

- Overview
- Architecture
- Core capabilities (what geospatial scientists can do)
- Agentic system (LLM + tools + workflow)
- GIS interoperability (QGIS / OGC / tiles)
- Data governance + audit
- Configuration (environment variables)
- Testing
- Optional/advanced stacks (GDAL, rasters)
- Frontend integration notes

## Overview

**Geo_Cortex_Assistant** is a **backend-only** geospatial API built with **FastAPI**. It provides:

- MODS dataset search and analysis (Postgres + PostGIS)
- Agentic querying (LLM-driven tool use + conversational summaries)
- Standard GIS access patterns (OGC API Features, MVT tiles, GeoJSON/CSV export)
- Data QA/QC utilities for geospatial specialists
- Geospatial file parsing (GeoJSON/KML/GPX/WKT + optional GDAL-backed formats)
- Optional raster workflows (upload, metadata, value sampling, XYZ PNG tiles)

Primary audience: **geospatial scientists/specialists** who need to query, validate, export, and visualize mineral occurrence data.

## Architecture

### Major components

- **FastAPI app**: `app/main.py`
- **Routers (API modules)**: `app/routers/*`
- **Services (business logic)**: `app/services/*`
- **Database**: PostgreSQL + PostGIS via SQLAlchemy + GeoAlchemy2
- **RAG**: FAISS vectorstore + local LLM runtime (Ollama)

### Data flow (typical)

1. User (or frontend) calls API endpoint (e.g., `/agent/workflow`).
2. Request gets a correlation id (`X-Request-Id`) via middleware.
3. Endpoint uses database (PostGIS) + RAG + tools to answer.
4. Governance layer records audit events to `audit.log` (when enabled).
5. Response returns:
   - a human-readable summary (`response`)
   - structured results (`occurrences`, `artifacts`)
   - optional chart specs (`artifacts.charts`)

### Persistence

- MODS occurrence table: `mods_occurrences`
- Job table for async operations: `jobs`
- Persistent agent sessions: `agent_sessions` (chat history + session state)

## Core capabilities (for geospatial scientists)

### Search, filter, and retrieve occurrences

- Attribute filtering (commodity, region, type, status)
- Bounding box queries
- Nearest-point queries (geodesic distance)
- Advanced polygon queries and spatial operations (intersects, buffer, nearest-to-geometry)

### QA/QC (data quality)

- Summary QC counts
- Duplicate MODS IDs
- Duplicate coordinate pairs
- Rule-based outlier checks (coordinates and bounds)

### Export / interoperability

- GeoJSON export for GIS tools and mapping
- CSV export (Excel-friendly UTF-8 BOM)
- Streaming CSV export for larger pulls (`stream=true`)

### File-based workflows

- Upload a geospatial file (AOI) and run spatial operations against it
- Agent can reuse AOI across requests (session memory)

### Raster workflows (optional)

- Upload rasters (GeoTIFF/COG)
- Background jobs compute metadata
- Sample a raster value at lon/lat
- Serve XYZ PNG tiles for GIS clients (QGIS XYZ layer)

## Agentic system (LLM + tools + workflow)

There are two agent styles:

### 1) Tool-loop agent (`/agent/`)

- Uses the LLM to:
  - interpret the user request
  - call tools (search/nearby/bbox/exports/QC/spatial/etc.)
  - produce a final conversational answer
- Returns:
  - `response` (human text)
  - `tool_trace` (what tools were called)
  - `occurrences` (when applicable)
  - `artifacts` (geojson/csv/spatial results, etc.)

### 2) Workflow agent (`/agent/workflow`)

Designed for “judge demo” and complex geospatial requests:

- Produces an explicit `plan` (steps with `action`, `args`, and `why`)
- Executes steps deterministically with governance checks and safety caps
- Produces an LLM-written summary grounded in **actual tool outputs**
- Adds chart-ready payloads (Vega-Lite) when applicable

#### Workflow offline mode

- `use_llm=false` runs tools and returns a deterministic summary.
- Global LLM controls exist via environment variables (see configuration).

### Persistent conversational memory

- Agent sessions are persisted in Postgres (`agent_sessions`):
  - last messages (up to 40)
  - state dict (AOI geometry, last links, etc.)
- This allows the agent to remain conversational across server restarts.

### Chart outputs (no frontend required)

Workflow responses may include `artifacts.charts` containing:

- `name`, `title`
- `data` (rows)
- `vega_lite` (a Vega-Lite v5 JSON spec referencing `"data": {"name": "data"}`)

These can be rendered by any Vega/Vega-Lite renderer in a UI or notebook.

## GIS interoperability

### OGC API Features (QGIS-ready)

Router: `app/routers/ogc.py`

Key endpoints:

- `GET /ogc` (landing)
- `GET /ogc/conformance`
- `GET /ogc/collections`
- `GET /ogc/collections/mods_occurrences/items`
  - filters: `bbox`, `commodity`, `region`, `occurrence_type`, `exploration_status`
  - paging: `limit`, `offset` (and `startindex`)
- `GET /ogc/collections/mods_occurrences/items/{id}`

Notes:

- Responses include `numberReturned` and `timeStamp`.
- `next/prev` links preserve query parameters.
- CRS is **EPSG:4326 (WGS84 / CRS84)**.

### Vector tiles (MVT)

Router: `app/routers/tiles.py`

- `GET /tiles/mvt/{z}/{x}/{y}.pbf` for high-performance point display in map clients.

### QGIS helper endpoints

Router: `app/routers/qgis.py`

- `GET /qgis/connection`: connection details derived from `DATABASE_URL` (password hidden by default)
- `GET /qgis/sql-examples`: copy/paste SQL examples for QGIS DB Manager

## Spatial operations

Router: `app/routers/spatial.py`

- `POST /spatial/query`: spatial intersects or dwithin using GeoJSON geometry
- `POST /spatial/buffer`: buffer any GeoJSON geometry by `distance_m`
- `POST /spatial/nearest`: nearest MODS points to an arbitrary GeoJSON geometry

These endpoints are also exposed as tools to the agent/workflow system.

## Files (geospatial parsing)

Router: `app/routers/files.py`  
Service: `app/services/geofile_service.py`

- `POST /files/parse` (multipart upload)
- `GET /files/formats`

Supported formats:

- **Pure Python (default)**: GeoJSON, KML, GPX, WKT
- **Optional GDAL stack**: GeoPackage (`.gpkg`), zipped Shapefile/FileGDB (`.zip`) when installed

## Jobs (long-running tasks)

Router: `app/routers/jobs.py`  
Service: `app/services/job_service.py`

- `GET /jobs/{job_id}` returns status/progress/result/error for background tasks.

## Rasters (optional)

Router: `app/routers/rasters.py`  
Service: `app/services/raster_service.py`

- `GET /rasters/formats`
- `POST /rasters/upload` (creates a job and computes metadata in background)
- `GET /rasters/{raster_id}/download`
- `GET /rasters/{raster_id}/value?lon=...&lat=...&band=1`
- `GET /rasters/{raster_id}/tiles/{z}/{x}/{y}.png`

## Data governance + audit

Service: `app/services/governance.py`

Implemented guardrails:

- **Feature flags** (strict mode optionally requires explicit enables)
- **Audit logging** (JSON lines to `audit.log`)
- **Response sanitization** (best-effort redaction of secrets/paths)
- **Audit rotation/retention** (best-effort):
  - rotates when file exceeds `AUDIT_LOG_MAX_BYTES`
  - keeps newest `AUDIT_LOG_MAX_FILES` rotated logs as `audit.<ts>.log`

## Configuration (environment variables)

Common:

- `DATABASE_URL` (Postgres/PostGIS connection string)
- `PUBLIC_BASE_URL` (used for agent-generated links; optional)

LLM (Ollama):

- `OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`)
- `OLLAMA_MODEL` (default `llama3.1`)
- `OLLAMA_EMBED_MODEL` (embeddings model, e.g. `nomic-embed-text`)
- `LLM_TIMEOUT_SEC` (default `20`)
- `LLM_DISABLED=true` (disable LLM calls; workflow still works with deterministic output)

Governance:

- `DATA_GOVERNANCE` (default `1`)
- `DATA_GOV_STRICT` (default `0`)
- `AUDIT_LOG_MAX_BYTES` (default `5242880`)
- `AUDIT_LOG_MAX_FILES` (default `5`)

Feature enables (only required if `DATA_GOV_STRICT=1`):

- `OGC_ENABLE=1`
- `QC_ENABLE=1`
- `EXPORT_ENABLE=1`
- `SPATIAL_ENABLE=1`
- `RASTERS_ENABLE=1`

Ingestion:

- `INGEST_ENABLE=1` to enable `/ingest/*`

Logging:

- `LOG_LEVEL` (default `INFO`)

## Testing

Smoke tests:

```bash
python scripts/smoke_test.py
```

Integration tests:

```bash
python -m pytest -q
```

Windows convenience:

```powershell
.\scripts\run_tests.ps1
```

## Frontend integration notes

The backend is ready for a frontend to consume.

Recommended “judge demo” UI flow:

- Chat panel -> call `POST /agent/workflow`
  - render `response`
  - render `plan` + `tool_trace` as expandable sections
- Map panel:
  - add OGC layer from `/ogc` (QGIS-style) or show GeoJSON from `artifacts.geojson`
  - optionally use `/tiles/mvt/...` for fast map display
- Charts panel:
  - render each entry in `artifacts.charts` using Vega-Lite
- File upload:
  - call `POST /agent/workflow/file` to load an AOI and run spatial workflows

## Notes / scope choices

- No authentication/authorization layer was added (capstone demo requirement).
- Many “production” concerns (rate limiting, multi-worker job queue, auth) can be added later without changing the core API shapes.

