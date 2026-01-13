## Setup Guide (detailed)

This guide is the detailed setup reference (environment variables, PostGIS, optional dependencies, troubleshooting).

### 1) Install dependencies

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
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

```bash
python scripts/load_mods_to_db.py
python scripts/build_vectorstore.py
```

### 5) Run the server

```bash
uvicorn app.main:app --reload --reload-dir "C:\Users\VICTUS\Geo_Cortex\Geo_Cortex_Assistant\app"
```

### 6) Tests

```bash
python scripts/smoke_test.py
python -m pytest -q
```

### Optional: enable more file formats (GDAL stack)

This enables parsing:

- GeoPackage (`.gpkg`)
- zipped Shapefile / FileGDB (`.zip`)

```bash
pip install -r requirements-gdal.txt
```

Check runtime support:

- `GET /files/formats`

### Optional: raster workflows (rasterio stack)

```bash
pip install -r requirements-raster.txt
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
