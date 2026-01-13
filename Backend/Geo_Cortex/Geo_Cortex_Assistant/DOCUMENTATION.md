## Documentation (complete reference)

This file is the “deep dive” reference for anyone implementing a frontend, extending the backend, or auditing behavior.

### Contents

- Data model
- Pipelines
- Agent endpoints (response contract)
- Geospatial ops (what exists + how to call it)
- GIS interoperability (OGC, tiles, QGIS)
- Governance + audit
- Testing + demos

## Data model (tables)

- **`mods_occurrences`**: MODS point dataset (EPSG:4326) with PostGIS `geom`
- **`jobs`**: persistent background jobs
- **`agent_sessions`**: persistent chat history + state (`last_aoi_geometry`, `last_uploaded_fc`)

## Pipelines

### Pipeline: database build

- On app startup (`app/main.py`):
  - `Base.metadata.create_all(bind=engine)`
  - `ensure_postgis_and_indexes(engine)`

### Pipeline: data load (MODS)

- `python scripts/load_mods_to_db.py` (recommended)
- Optional upload:
  - `POST /ingest/mods-csv` (requires `INGEST_ENABLE=1`)

### Pipeline: embeddings (RAG)

- `python scripts/build_vectorstore.py` builds FAISS embeddings for MODS text.

### Pipeline: agent workflow

- `POST /agent/workflow`
- `POST /agent/workflow/file` (uploads FeatureCollection + stores AOI + enables dissolve/joins/overlay)

## Agent response contract

Workflow response includes:

- `response` (human summary; LLM or deterministic fallback)
- `plan` (explicit steps)
- `tool_trace` (traceability)
- `occurrences` (when the tool outputs include MODS rows)
- `artifacts` (structured outputs; may include `charts`)

## Geospatial ops (API)

### MODS vs geometry

- `POST /spatial/query` (intersects/dwithin)
- `POST /spatial/buffer`
- `POST /spatial/nearest`

### Vector GIS toolbox

- `POST /spatial/overlay`
- `POST /spatial/dissolve`
- `POST /spatial/join/mods/counts`
- `POST /spatial/join/mods/nearest`

### QC / QA

- `GET /qc/summary`
- `GET /qc/duplicates/mods-id`
- `GET /qc/duplicates/coords`
- `GET /qc/outliers`

### Exports

- `GET /export/geojson`
- `GET /export/csv` (supports `stream=true`)

## GIS interoperability

- OGC API Features:
  - `GET /ogc`
  - `GET /ogc/collections/mods_occurrences/items`
- MVT tiles:
  - `GET /tiles/mvt/{z}/{x}/{y}.pbf`
- QGIS helpers:
  - `GET /qgis/sql-examples`
  - `GET /qgis/connection`

## Files / formats

- `GET /files/formats`
- `POST /files/parse`

Pure python: GeoJSON/KML/GPX/WKT  
Optional GDAL: GeoPackage + zipped Shapefile/FGDB

## Rasters (optional)

- `POST /rasters/upload`
- `GET /jobs/{job_id}`
- `GET /rasters/{raster_id}/tiles/{z}/{x}/{y}.png`
- `GET /rasters/{raster_id}/value`
- `POST /rasters/{raster_id}/zonal-stats`

## Governance + audit

- Audit file: `audit.log` (JSON lines)
- Rotation:
  - `AUDIT_LOG_MAX_BYTES`
  - `AUDIT_LOG_MAX_FILES`
- Feature gating (strict mode):
  - `DATA_GOV_STRICT=1` + `*_ENABLE=1`

## Testing + demos

- Smoke: `python scripts/smoke_test.py`
- Pytest: `python -m pytest -q`
- Demo ops: `python scripts/demo_ops.py`

