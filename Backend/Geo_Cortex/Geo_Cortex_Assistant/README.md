# 🗺️ Geo_Cortex_Assistant

**Geo_Cortex_Assistant** is an intelligent, API-driven virtual assistant built using **FastAPI**, designed to help geologists and researchers explore mineral occurrences and geological data from the MODS (Mineral Occurrence Database System) dataset.

---

## 🌟 Features

- 🌐 Public API (no login/auth)
- 📍 Search MODS geological occurrences (including PostGIS geo queries)
- 🧠 Agentic RAG: answers + runs small data processes (counts/filters/nearby)
- 📦 Modular FastAPI design for scalable deployment
- 🔍 Advanced search and filtering of geological data

---

## 🚀 Tech Stack

- **FastAPI** – Web API framework
- **PostgreSQL + PostGIS / SQLAlchemy** – Database + geo queries
- **Ollama (local models)** – LLM + embeddings
- **FAISS** – Vector store for RAG

---

## 📡 API Endpoints

### 📍 Occurrence Endpoints

| Method | Endpoint                          | Description                |
|--------|-----------------------------------|----------------------------|
| GET    | `/occurrences/mods/search`        | Filter/search MODS rows    |
| GET    | `/occurrences/mods/bbox`          | Bounding box filter        |
| GET    | `/occurrences/mods/nearest`       | Nearest-by-distance        |
| GET    | `/occurrences/mods/{id}`          | Fetch MODS row by DB id    |

---

### 🧭 OGC API Features (QGIS-ready)

| Method | Endpoint                                           | Description |
|--------|----------------------------------------------------|-------------|
| GET    | `/ogc`                                              | Landing     |
| GET    | `/ogc/collections`                                  | Collections |
| GET    | `/ogc/collections/mods_occurrences/items`           | Features    |
| GET    | `/ogc/collections/mods_occurrences/items/{item_id}` | Feature by id |

---

### ✅ QC / QA (data quality)

| Method | Endpoint                       | Description |
|--------|--------------------------------|-------------|
| GET    | `/qc/summary`                  | QC summary counts |
| GET    | `/qc/duplicates/mods-id`       | Duplicate MODS IDs |
| GET    | `/qc/duplicates/coords`        | Duplicate coordinate pairs |
| GET    | `/qc/outliers`                 | Rule-based outliers |

---

### 🧠 RAG / Agent Endpoints

| Method | Endpoint        | Description                  |
|--------|-----------------|------------------------------|
| POST   | `/query/`       | RAG answer + occurrences      |
| POST   | `/query/rag`    | Same as `/query/`             |
| POST   | `/agent/`       | Agentic: can run tools first  |
| POST   | `/agent/workflow` | Workflow agent: returns explicit plan + executes it |
| POST   | `/agent/workflow/file` | Workflow agent + geospatial file upload (AOI) |

---

### 🧰 QGIS helpers

| Method | Endpoint              | Description |
|--------|------------------------|-------------|
| GET    | `/qgis/connection`     | PostGIS connection info (password hidden by default) |
| GET    | `/qgis/sql-examples`   | Copy/paste SQL for QGIS DB Manager |

---

## 📥 Setup & Installation

### 1. Clone the Repo
```bash
cd Geo_Cortex_Assistant
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Environment Variables

Create a `.env` file:
```
DATABASE_URL=postgresql+psycopg2://postgres:209810@localhost:5432/geocortex_assistant
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1
OLLAMA_EMBED_MODEL=nomic-embed-text

# Optional (agent-generated links)
PUBLIC_BASE_URL=http://127.0.0.1:8000

# Optional governance
DATA_GOVERNANCE=1
DATA_GOV_STRICT=0
```

### 5. Initialize Database

```bash
python scripts/load_mods_to_db.py
```

### 6. Build Vector Store (FAISS)

```bash
python scripts/build_vectorstore.py
```

### 7. Run the API

```bash
uvicorn app.main:app --reload
```

> Visit `http://127.0.0.1:8000/docs` for Swagger UI

---

## 🧠 RAG & LLM Integration

* `POST /query/` and `POST /query/rag`: FAISS retrieval + Ollama LLM answer.
* `POST /agent/`: An agent loop that can run small tools (search/count/nearby) before answering.
* `POST /agent/workflow`: A workflow-style agent that returns an explicit plan (`plan`) and tool trace (`tool_trace`).

LLM runtime controls:
- `LLM_TIMEOUT_SEC=20` (default): hard timeout for Ollama calls
- `LLM_DISABLED=true`: disable LLM calls entirely (endpoints still work, but responses are deterministic/fallback)

---

## ✅ Testing

### Smoke test (quick)

```bash
python scripts/smoke_test.py
```

### Pytest integration tests

Start the server in one terminal, then run:

```bash
pip install -r requirements-dev.txt
pytest
```

### One command (Windows PowerShell)

```powershell
.\scripts\run_tests.ps1
```

---

## 🗺️ Use from QGIS (recommended)

### Option A: OGC API Features layer
- In QGIS: **Data Source Manager** → **OGC API - Features** (or similar, depends on QGIS version)
- Create a new connection using the service URL:
  - `http://127.0.0.1:8000/ogc`
- Add the `mods_occurrences` collection as a layer.

Common filters (as query params on `/items`): `bbox`, `commodity`, `region`, `occurrence_type`, `exploration_status`, `limit`, `offset`.

CRS/SRID: data is stored and served in **EPSG:4326**.

### Option B: Direct PostGIS connection
- Use `/qgis/connection` to get host/port/database/username details (requires `DATABASE_URL` to be set).
- Password is omitted unless you set `QGIS_EXPOSE_PASSWORD=1`.

## 🛡️ Governance + audit
- Audit log file: `Geo_Cortex_Assistant/audit.log`
- Audit rotation (best-effort):
  - `AUDIT_LOG_MAX_BYTES=5242880` (5MB default)
  - `AUDIT_LOG_MAX_FILES=5` (keeps newest rotations as `audit.<ts>.log`)
- If you enable strict mode (`DATA_GOV_STRICT=1`), you can explicitly allow features:
  - `OGC_ENABLE=1`, `QC_ENABLE=1`, `EXPORT_ENABLE=1`, `ADVANCED_ENABLE=1`

Units:
- `/occurrences/mods/search` uses `radius_km` in kilometers.
- Nearest distances are computed in meters (PostGIS geography), returned as `distance_m`.

Query caps (defaults are conservative):
- `/ogc/collections/mods_occurrences/items`: `limit` max 1000
- `/qc/duplicates/*` and `/qc/outliers`: `limit` max 5000

---

## 📁 Geospatial file support (uploads)

- **Pure Python (works out of the box)**: GeoJSON, KML, GPX, WKT via `POST /files/parse`
- **Optional GDAL stack**: GeoPackage (`.gpkg`) and zipped Shapefile/FileGDB (`.zip`)

Check what your runtime supports:
- `GET /files/formats`

Install optional stack:

```bash
pip install -r requirements-gdal.txt
```

Note: on Windows + Python 3.14, some GDAL-backed wheels may not be available. If pip fails, use Conda for GDAL packages.

---

## 🛰️ Raster support (optional)

Raster workflows are optional and enabled via `/rasters/*`.

- Check availability: `GET /rasters/formats`
- Upload a GeoTIFF/COG: `POST /rasters/upload` (creates a job you can poll at `/jobs/{job_id}`)
- Sample a value (if rasterio is available and CRS is EPSG:4326): `GET /rasters/{raster_id}/value?lon=...&lat=...`

Install optional raster stack:

```bash
pip install -r requirements-raster.txt
```

Note: on Windows + Python 3.14, rasterio wheels may not be available. If pip fails, use Conda for rasterio.
## 📁 Folder Structure

```
Geo_Cortex_Assistant/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── database.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── dbmodels.py
│   │   └── schemas.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── occurrences.py
│   │   ├── llm.py
│   │   └── agent.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── agent_service.py
│   │   ├── db_maintenance.py
│   │   ├── llm_service.py
│   │   ├── retriever_service.py
│   │   └── router_service.py
│   └── vectorstores/
│       ├── __init__.py
│       └── loader.py
├── scripts/
│   └── build_vectorstore.py
├── MODS.csv
├── requirements.txt
└── README.md
```

---

## 📜 License

Copyright (c) 2025

All rights reserved.

---

## 📬 Contact

For inquiries, please contact the development team.
