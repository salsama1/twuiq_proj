## Geo_Cortex_Assistant (Backend) — Complete Guide

This is the **single source of truth** for how the project works: **architecture**, **data model**, **pipelines**, **endpoints**, **agent behavior**, **testing**, and **frontend integration**.

### Quick links

- **Swagger UI**: `http://127.0.0.1:8000/docs`
- **OpenAPI JSON**: `http://127.0.0.1:8000/openapi.json`
- **Health**: `http://127.0.0.1:8000/health`

### What this system is

**Geo_Cortex_Assistant** is a **backend-only geospatial platform** built with **FastAPI** for geospatial scientists. It combines:

- **PostGIS** for spatial data + spatial querying
- **RAG (FAISS embeddings)** for context-grounded question answering on MODS content
- An **agentic workflow layer** that turns natural language into multi-step geospatial operations, returning:
  - **human summaries**
  - **structured results**
  - **GIS-ready outputs** (OGC links, GeoJSON/CSV, tiles)
  - **charts** (Vega-Lite specs + data)

No authentication was added (capstone demo scope).

## Tech stack

- **API**: FastAPI + Uvicorn
- **DB**: PostgreSQL + PostGIS + SQLAlchemy + GeoAlchemy2
- **RAG**: FAISS vector store
- **LLM runtime**: Ollama (local)
- **Geometry ops**: PostGIS + Shapely
- **Optional file parsing**: GDAL stack (Fiona) for GeoPackage / zipped Shapefile/FGDB
- **Optional raster**: rasterio + numpy + pillow

## Architecture (how it is structured)

### Code layout

```
Geo_Cortex_Assistant/
├── app/
│   ├── main.py                 # FastAPI app + middleware + router wiring
│   ├── database.py             # SQLAlchemy engine/session/base
│   ├── models/
│   │   ├── dbmodels.py         # ORM tables: mods_occurrences, jobs, agent_sessions
│   │   └── schemas.py          # Pydantic request/response models
│   ├── routers/                # API surface (modular)
│   └── services/               # business logic (agent, RAG, governance, parsing, rasters)
├── scripts/                    # CLI utilities + demos
├── demo_inputs/                # demo GeoJSON inputs for the GIS toolbox
├── tests/                      # integration tests (pytest)
├── MODS.csv                    # base dataset (also used for embeddings)
└── audit.log                   # governance/audit output (JSON lines)
```

### Runtime request pipeline (high level)

1. **Client calls an endpoint** (UI/QGIS/script).
2. Middleware adds **`X-Request-Id`** and logs method/path/status/latency.
3. Router executes logic (DB query, RAG retrieval, spatial ops, etc.).
4. Governance records **audit events** (if enabled).
5. Response returns **human text + structured artifacts**.

### System flowchart (pipelines)

```mermaid
flowchart TD
  QGIS[QGISClient] --> OGC[OGCApiFeatures]
  QGIS --> DB[PostGIS]
  Analyst[SpecialistUser] --> Agent[AgentEndpoint]
  Agent --> Tools[GeoTools]
  Tools --> DB
  Tools --> Exports[ExportEndpoints]
  Tools --> QC[QCEndpoints]
  Tools --> OGC
  Gov[DataGovernance] --> Agent
  Gov --> Exports
  Gov --> QC
```

### Agentic system flowchart (internal)

```mermaid
flowchart TD
  User[Human user] --> API[FastAPI]
  API --> RID[X-Request-Id middleware]
  RID --> Route{Which endpoint?}

  Route --> WF[POST /agent/workflow]
  Route --> WFF[POST /agent/workflow/file]
  Route --> AG[POST /agent/]

  %% session + memory
  WF --> Sess[(agent_sessions\nchat + state)]
  WFF --> Sess
  AG --> Sess

  %% file intake
  WFF --> Parse[Parse geospatial file\n(files/parse logic)]
  Parse --> FC[Uploaded FeatureCollection]
  FC --> AOI[Union AOI geometry]
  FC --> MemFC[Store FeatureCollection in session]
  AOI --> MemAOI[Store AOI geometry in session]

  %% retrieval + planning
  WF --> RAG[FAISS retrieval\n(MODS embeddings)]
  AG --> RAG
  RAG --> Plan{Plan mode}
  Plan -->|deterministic rules| Steps[Tool plan]
  Plan -->|LLM planner (optional)| LLMPlan[LLM plan JSON]
  LLMPlan --> Steps

  %% tool execution (governed)
  Steps --> Gov[Data governance\nfeature flags + audit]
  Gov --> Tools[Tool execution]
  Tools --> DB[PostGIS queries]
  Tools --> Spatial[Spatial ops\n(intersects/dwithin/buffer/nearest/overlay/dissolve/joins)]
  Tools --> Exports[Exports\n(GeoJSON/CSV/OGC links/tiles)]
  Tools --> QC[QC/QA checks]
  Tools --> Raster[Raster ops\n(tiles/value/zonal stats)]

  %% summarize + visualize
  Tools --> Artifacts[Artifacts\n(geojson/csv/qgis links/etc.)]
  Artifacts --> Charts[Vega-Lite charts\n(artifacts.charts)]
  Artifacts --> Summary{Summarize}
  Summary -->|LLM enabled| LLMSum[LLM summary\n(timeout protected)]
  Summary -->|LLM disabled/timeout| AutoSum[Deterministic summary]
  LLMSum --> Resp[API response]
  AutoSum --> Resp
  Resp --> User
```

## Data model (tables)

### `mods_occurrences`

Main geospatial dataset (MODS points). Stores:

- lat/lon fields + a PostGIS **`geom`** column (geography POINT, EPSG:4326)
- commodity/region/type/status fields and additional attributes

### `jobs`

Persistent job tracking for background tasks (e.g., raster metadata computation).

### `agent_sessions`

Persistent chat + state:

- last 40 chat messages
- session state (e.g., last AOI geometry, last uploaded FeatureCollection)

## Pipelines (how the system “does work”)

### Pipeline A — Build the database

- On startup (`app/main.py`):
  - creates tables (`Base.metadata.create_all`)
  - ensures PostGIS + indexes (`ensure_postgis_and_indexes`)
- Populate MODS rows:
  - `python scripts/load_mods_to_db.py`
  - or `POST /ingest/mods-csv` (disabled unless `INGEST_ENABLE=1`)

### Pipeline B — Build the RAG embeddings (MODS)

1. `python scripts/build_vectorstore.py`
2. Embeddings are stored in a FAISS vector store.
3. Query endpoints retrieve relevant chunks and optionally call the LLM.

### Pipeline C — Agentic workflow (fast + traceable)

Endpoint: `POST /agent/workflow` (or `/agent/workflow/file`)

1. **Plan**
   - deterministic keyword planning for common GIS requests (fast)
   - optionally LLM planning (when enabled)
2. **Execute**
   - runs tools (DB queries, spatial ops, QC, exports, joins, etc.)
   - produces `plan` + `tool_trace`
3. **Summarize**
   - if LLM enabled, summarizes **actual tool outputs**
   - if LLM times out, returns a deterministic summary
4. **Visualize**
   - returns chart-ready payloads in `artifacts.charts` (Vega-Lite specs + data)

### Pipeline D — File upload → geometry ops

Endpoints:

- `POST /files/parse` (turns a geospatial file into a GeoJSON FeatureCollection)
- `POST /agent/workflow/file` (upload file and run geospatial workflow)

The system stores:

- union geometry (AOI) for intersects/buffer/nearest
- the full FeatureCollection (so dissolve/overlay/joins can be executed by the agent)

### Pipeline E — Raster upload → tiles/values/zonal stats (optional)

Endpoints:

- `POST /rasters/upload` → creates a `job_id` and saves the raster
- `GET /jobs/{job_id}` → check status/result
- `GET /rasters/{raster_id}/tiles/{z}/{x}/{y}.png` → XYZ tiles
- `GET /rasters/{raster_id}/value` → sample a value (requires EPSG:4326)
- `POST /rasters/{raster_id}/zonal-stats` → polygon/geometry statistics

## API surface (endpoints by category)

### Core

- `GET /health`
- `GET /version`

### MODS (database queries)

- `GET /occurrences/mods/search`
- `GET /occurrences/mods/bbox`
- `GET /occurrences/mods/nearest`
- `GET /occurrences/mods/{id}`

### Advanced search

- `POST /advanced/mods` (multi-filters + polygon/MultiPolygon)

### Spatial ops (MODS vs geometry)

- `POST /spatial/query` (intersects / dwithin)
- `POST /spatial/buffer` (geometry buffer polygon)
- `POST /spatial/nearest` (nearest MODS points to any geometry)

### Vector GIS toolbox (pure geometry ops)

- `POST /spatial/overlay` (union/intersection/difference/symmetric_difference)
- `POST /spatial/dissolve` (FeatureCollection → dissolved by property)
- `POST /spatial/join/mods/counts` (polygons → MODS point counts)
- `POST /spatial/join/mods/nearest` (features → nearest MODS point)

### QC / QA

- `GET /qc/summary`
- `GET /qc/duplicates/mods-id`
- `GET /qc/duplicates/coords`
- `GET /qc/outliers`

### Export

- `GET /export/geojson`
- `GET /export/csv` (supports `stream=true` for streaming)

### OGC API Features (QGIS-ready)

- `GET /ogc`
- `GET /ogc/conformance`
- `GET /ogc/collections`
- `GET /ogc/collections/mods_occurrences/items`
- `GET /ogc/collections/mods_occurrences/items/{id}`

### Tiles

- `GET /tiles/mvt/{z}/{x}/{y}.pbf`

### Agent / RAG

- `POST /query/` and `POST /query/rag`
- `POST /agent/`
- `POST /agent/workflow`
- `POST /agent/workflow/file`
- `POST /agent/reset`

### Files

- `GET /files/formats`
- `POST /files/parse`

### Jobs

- `GET /jobs/{job_id}`

### Rasters (optional)

- `GET /rasters/formats`
- `POST /rasters/upload`
- `GET /rasters/{raster_id}/download`
- `GET /rasters/{raster_id}/value`
- `GET /rasters/{raster_id}/tiles/{z}/{x}/{y}.png`
- `POST /rasters/{raster_id}/zonal-stats`

## Agent response contract (what a frontend renders)

All agent endpoints return:

- `response`: human summary text
- `plan` (workflow only): steps
- `tool_trace`: what ran (traceability)
- `occurrences`: structured MODS rows (when relevant)
- `artifacts`: structured outputs
  - exports: `geojson`, `csv`
  - spatial: `spatial_geojson`, `spatial_buffer_geometry`, etc.
  - charts: `charts` (Vega-Lite specs + data)

## Setup (local)

### 1) Install

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2) Configure `.env`

```
DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/geocortex_assistant
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1
OLLAMA_EMBED_MODEL=nomic-embed-text
PUBLIC_BASE_URL=http://127.0.0.1:8000
```

### 3) Build database + embeddings

```bash
python scripts/load_mods_to_db.py
python scripts/build_vectorstore.py
```

### 4) Run the server

```bash
uvicorn app.main:app --reload --reload-dir "C:\Users\VICTUS\Geo_Cortex\Geo_Cortex_Assistant\app"
```

## Governance + audit (what it logs)

- Audit file: `audit.log` (JSON lines)
- Rotation (best-effort):
  - `AUDIT_LOG_MAX_BYTES=5242880`
  - `AUDIT_LOG_MAX_FILES=5`

Feature gating:

- `DATA_GOVERNANCE=1`
- `DATA_GOV_STRICT=0` (set to `1` to require explicit `*_ENABLE=1`)

## Optional dependencies (enable more file/raster support)

### GDAL-backed files (GeoPackage + zipped Shapefile/FGDB)

```bash
pip install -r requirements-gdal.txt
```

### Raster stack (rasterio tiles + zonal stats)

```bash
pip install -r requirements-raster.txt
```

## LLM controls (speed + offline)

- `LLM_TIMEOUT_SEC=20` (default)
- `LLM_DISABLED=true` (disable LLM calls; workflow still returns deterministic summaries)

## Testing (repeatable)

### Smoke test

```bash
python scripts/smoke_test.py
```

### Integration tests

```bash
python -m pytest -q
```

### Demo script (calls overlay/dissolve/joins)

```bash
python scripts/demo_ops.py
```

## Frontend integration (recommended approach)

To build a demo UI without guessing:

- Use **`POST /agent/workflow`** as your main “chat” call.
- Render **maps** using:
  - OGC API Features (`/ogc/...`) or GeoJSON from `artifacts.geojson`
  - MVT tiles (`/tiles/mvt/...`) for fast point rendering
- Render **charts** using `artifacts.charts` (Vega-Lite).
- Support **file upload** via `POST /agent/workflow/file`.

## Troubleshooting

- If the response says **LLM timed out**:
  - ensure Ollama is running: `ollama serve`
  - increase `LLM_TIMEOUT_SEC`
  - or set `use_llm=false` for workflow calls
- If `GET /files/formats` reports `gdal_available=false`:
  - install `requirements-gdal.txt`
