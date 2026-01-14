## Setup Guide (detailed)

This guide is the detailed setup reference (environment variables, PostGIS, optional dependencies, troubleshooting).

### 1) Install dependencies

**Recommended (Windows / PowerShell, uses Python 3.12):**

```powershell
# If you have multiple Pythons installed, prefer 3.12 for best wheel support on Windows.
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
```

If you already created `.venv`, just reinstall:

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
```

### 2) PostgreSQL + PostGIS

Create a database and enable PostGIS:

```sql
CREATE DATABASE geocortex_assistant;
\c geocortex_assistant
CREATE EXTENSION IF NOT EXISTS postgis;
```

### 3) Configure `.env`

Create `Geo_Cortex_Assistant/.env`:

```
DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/geocortex_assistant
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1
OLLAMA_EMBED_MODEL=nomic-embed-text
PUBLIC_BASE_URL=http://127.0.0.1:8000

# LLM controls
LLM_TIMEOUT_SEC=20
# LLM_DISABLED=true

# Governance (enabled by default)
DATA_GOVERNANCE=1
DATA_GOV_STRICT=0
AUDIT_LOG_MAX_BYTES=5242880
AUDIT_LOG_MAX_FILES=5

# Ingest endpoints (disabled by default)
# INGEST_ENABLE=1
```

### 4) Load data + embeddings

```powershell
.\.venv\Scripts\python scripts/load_mods_to_db.py
.\.venv\Scripts\python scripts/build_vectorstore.py
```

### 5) Run the server

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

### 6) Tests

```powershell
.\.venv\Scripts\python scripts/smoke_test.py
.\.venv\Scripts\python -m pytest -q
```

### 7) (Optional) Evaluated accuracy report

This prints golden + holdout metrics and **Wilson 95% lower bounds**:

```powershell
.\.venv\Scripts\python scripts/report_accuracy_claims.py
```

### Optional: enable more file formats (GDAL stack)

This enables parsing:

- GeoPackage (`.gpkg`)
- zipped Shapefile / FileGDB (`.zip`)

```powershell
.\.venv\Scripts\python -m pip install -r requirements-gdal.txt
```

Check runtime support:

- `GET /files/formats`

### Optional: raster workflows (rasterio stack)

```powershell
.\.venv\Scripts\python -m pip install -r requirements-raster.txt
```

Check runtime support:

- `GET /rasters/formats`

### Troubleshooting

- **LLM timed out**:
  - run `ollama serve`
  - increase `LLM_TIMEOUT_SEC`
  - or use `use_llm=false` on `/agent/workflow`
- **GDAL formats not available** (`gdal_available=false`):
  - install `requirements-gdal.txt` (Conda may be easier on Windows)
