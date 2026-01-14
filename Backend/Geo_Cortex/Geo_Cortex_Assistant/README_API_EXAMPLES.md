# Geo_Cortex_Assistant API Examples (Copy/Paste)

This is a practical “how to test the API” guide with **ready-to-run examples** for each endpoint documented in `DOCUMENTATION.md` (plus a few helper endpoints that exist in the app).

## Quick setup

- **Base URL**: by default the API runs at `http://127.0.0.1:8000`
- **Swagger UI**: `http://127.0.0.1:8000/docs`

### Set `BASE_URL` (PowerShell)

```powershell
$BASE_URL = "http://127.0.0.1:8000"
$env:BASE_URL = $BASE_URL
```

### Use `curl.exe` on Windows

PowerShell aliases `curl` to `Invoke-WebRequest`. To avoid surprises, use **`curl.exe`** in the examples below.

---

## Health + metadata

### `GET /` (root)

- **What it does**: Confirms the API is reachable and shows where docs live.
- **Good for**: “Is the server up?” quick check.

```powershell
curl.exe "$env:BASE_URL/"
```

### `GET /health`

- **What it does**: Lightweight health check endpoint.
- **Good for**: CI/smoke tests.

```powershell
curl.exe "$env:BASE_URL/health"
```

### `GET /version`

- **What it does**: Runtime/build info (python version, platform, optional git sha).
- **Good for**: Confirming which build is deployed.

```powershell
curl.exe "$env:BASE_URL/version"
```

---

## Agent endpoints (LLM + tools)

These endpoints return a structured payload containing:
- `response`: the final user-facing answer (LLM or deterministic fallback)
- `tool_trace`: traceability of tool calls
- `occurrences`: rows returned by tools (when applicable)
- `artifacts`: structured outputs (tables/charts/etc)
- `session_id`: chat/session memory key

### `POST /agent/`

- **What it does**: “Agentic RAG” — the model can run small tools (search/nearby/count) before answering.
- **When to use**: Conversational Q&A over the dataset without explicit workflow planning.

**Request body (JSON):**

```json
{
  "query": "string",
  "max_steps": 3,
  "session_id": "string"
}
```

```powershell
$body = @'
{
  "query": "Show me gold occurrences in Riyadh and summarize patterns.",
  "max_steps": 3
}
'@
curl.exe -sS -X POST "$env:BASE_URL/agent/" -H "Content-Type: application/json" --data-binary $body
```

### `POST /agent/file`

- **What it does**: Same as `/agent/`, but you attach a geospatial file that becomes “uploaded geometry context”.
- **When to use**: When your question depends on an AOI polygon/lines/points you provide.

```powershell
curl.exe -sS -X POST "$env:BASE_URL/agent/file" -F "query=Find the nearest occurrences to this AOI and summarize the top commodities." -F "max_steps=3" -F "file=@demo_inputs\aoi.geojson"
```

### `POST /agent/workflow`

- **What it does**: Returns an explicit **plan** (`plan`) and executes it.
- **When to use**: You want a defensible plan + tool execution trace.

**Request body (JSON):**

```json
{
  "query": "string",
  "max_steps": 6,
  "use_llm": true,
  "session_id": "string"
}
```

```powershell
$body = @'
{
  "query": "Give me QC summary, top commodities, and counts by region.",
  "max_steps": 6,
  "use_llm": true
}
'@
curl.exe -sS -X POST "$env:BASE_URL/agent/workflow" -H "Content-Type: application/json" --data-binary $body
```

### `POST /agent/workflow/file`

- **What it does**: Workflow + file upload; stores uploaded AOI into session memory so you can call `/agent/workflow` later without re-uploading.
- **When to use**: A workflow that depends on uploaded geometry (buffer/overlay/dissolve/joins).

```powershell
curl.exe -sS -X POST "$env:BASE_URL/agent/workflow/file" -F "query=Buffer the uploaded AOI by 50km, then return occurrences within the buffer and summarize." -F "max_steps=6" -F "use_llm=true" -F "file=@demo_inputs\aoi.geojson"
```

### `POST /agent/reset?session_id=...`

- **What it does**: Best-effort reset of server-side session memory (chat history + stored AOI/featurecollection).
- **When to use**: You want a clean slate for a given session.

```powershell
$sid = "replace-with-session-id"
curl.exe -s -X POST "$env:BASE_URL/agent/reset?session_id=$sid"
```

---

## Spatial ops (MODS vs geometry) — `POST /spatial/...`

All spatial endpoints require a GeoJSON **geometry object** (not a full FeatureCollection) unless explicitly stated.

### `POST /spatial/query`

- **What it does**: Query MODS points using a geometry predicate:
  - `op=intersects`: points intersecting the geometry
  - `op=dwithin`: points within `distance_m` (meters) of the geometry
- **Useful filters**: `commodity`, `region`, `occurrence_type`, `exploration_status`
- **Optional**: `return_geojson=true` returns a FeatureCollection of the results

**Request body (JSON):**

```json
{
  "op": "intersects",
  "geometry": { "type": "Polygon", "coordinates": [[[46.0, 24.0], [47.0, 24.0], [47.0, 25.0], [46.0, 25.0], [46.0, 24.0]]] },
  "commodity": "Gold",
  "region": "Riyadh",
  "occurrence_type": "string",
  "exploration_status": "string",
  "limit": 50,
  "offset": 0,
  "return_geojson": true
}
```

```powershell
$body = @'
{
  "op": "intersects",
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      [
        [46.0, 24.0],
        [47.0, 24.0],
        [47.0, 25.0],
        [46.0, 25.0],
        [46.0, 24.0]
      ]
    ]
  },
  "commodity": "Gold",
  "limit": 50,
  "offset": 0,
  "return_geojson": true
}
'@
curl.exe -sS -X POST "$env:BASE_URL/spatial/query" -H "Content-Type: application/json" --data-binary $body
```

### `POST /spatial/buffer`

- **What it does**: Buffers an input geometry by `distance_m` (meters) and returns the buffer polygon geometry.

**Request body (JSON):**

```json
{
  "distance_m": 50000,
  "geometry": { "type": "Point", "coordinates": [46.6753, 24.7136] }
}
```

```powershell
$body = @'
{
  "distance_m": 50000,
  "geometry": { "type": "Point", "coordinates": [46.6753, 24.7136] }
}
'@
curl.exe -sS -X POST "$env:BASE_URL/spatial/buffer" -H "Content-Type: application/json" --data-binary $body
```

### `POST /spatial/nearest`

- **What it does**: Finds nearest MODS points to a geometry (distance computed in meters).

**Request body (JSON):**

```json
{
  "geometry": { "type": "Point", "coordinates": [46.6753, 24.7136] },
  "limit": 10,
  "commodity": "Gold",
  "region": "Riyadh",
  "occurrence_type": "string",
  "exploration_status": "string"
}
```

```powershell
$body = @'
{
  "geometry": { "type": "Point", "coordinates": [46.6753, 24.7136] },
  "limit": 10,
  "commodity": "Gold"
}
'@
curl.exe -sS -X POST "$env:BASE_URL/spatial/nearest" -H "Content-Type: application/json" --data-binary $body
```

---

## Vector GIS toolbox — `POST /spatial/...`

### `POST /spatial/overlay`

- **What it does**: Overlay two GeoJSON geometries (no DB needed).
- **Ops**: `union | intersection | difference | symmetric_difference`

**Request body (JSON):**

```json
{
  "op": "intersection",
  "a": { "type": "Polygon", "coordinates": [[[46, 24], [47, 24], [47, 25], [46, 25], [46, 24]]] },
  "b": { "type": "Polygon", "coordinates": [[[46.5, 24.5], [47.5, 24.5], [47.5, 25.5], [46.5, 25.5], [46.5, 24.5]]] }
}
```

```powershell
$body = @'
{
  "op": "intersection",
  "a": {
    "type": "Polygon",
    "coordinates": [[[46,24],[47,24],[47,25],[46,25],[46,24]]]
  },
  "b": {
    "type": "Polygon",
    "coordinates": [[[46.5,24.5],[47.5,24.5],[47.5,25.5],[46.5,25.5],[46.5,24.5]]]
  }
}
'@
curl.exe -sS -X POST "$env:BASE_URL/spatial/overlay" -H "Content-Type: application/json" --data-binary $body
```

### `POST /spatial/dissolve`

- **What it does**: Dissolve an input **FeatureCollection** by a property key, producing one output feature per unique property value.

**Request body (JSON):**

```json
{
  "by_property": "group",
  "max_features": 10000,
  "feature_collection": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": { "type": "Polygon", "coordinates": [[[46, 24], [47, 24], [47, 25], [46, 25], [46, 24]]] },
        "properties": { "group": "A", "id": 1 }
      }
    ]
  }
}
```

```powershell
$body = @'
{
  "by_property": "group",
  "max_features": 10000,
  "feature_collection": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": { "type": "Polygon", "coordinates": [[[46,24],[47,24],[47,25],[46,25],[46,24]]] },
        "properties": { "group": "A", "id": 1 }
      },
      {
        "type": "Feature",
        "geometry": { "type": "Polygon", "coordinates": [[[47,24],[48,24],[48,25],[47,25],[47,24]]] },
        "properties": { "group": "A", "id": 2 }
      }
    ]
  }
}
'@
curl.exe -sS -X POST "$env:BASE_URL/spatial/dissolve" -H "Content-Type: application/json" --data-binary $body
```

### `POST /spatial/join/mods/counts`

- **What it does**: For each polygon feature in the input FeatureCollection, counts intersecting MODS points and adds `mods_count` to properties.

**Request body (JSON):**

```json
{
  "predicate": "intersects",
  "id_property": "id",
  "max_features": 2000,
  "feature_collection": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": { "type": "Polygon", "coordinates": [[[46, 24], [47, 24], [47, 25], [46, 25], [46, 24]]] },
        "properties": { "id": "poly-1" }
      }
    ]
  }
}
```

```powershell
$body = @'
{
  "predicate": "intersects",
  "id_property": "id",
  "max_features": 2000,
  "feature_collection": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": { "type": "Polygon", "coordinates": [[[46,24],[47,24],[47,25],[46,25],[46,24]]] },
        "properties": { "id": "poly-1" }
      }
    ]
  }
}
'@
curl.exe -sS -X POST "$env:BASE_URL/spatial/join/mods/counts" -H "Content-Type: application/json" --data-binary $body
```

### `POST /spatial/join/mods/nearest`

- **What it does**: For each input feature, finds the nearest MODS point and distance.

**Request body (JSON):**

```json
{
  "id_property": "id",
  "limit_features": 200,
  "feature_collection": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": { "type": "Point", "coordinates": [46.6753, 24.7136] },
        "properties": { "id": "pt-1" }
      }
    ]
  }
}
```

```powershell
$body = @'
{
  "id_property": "id",
  "limit_features": 200,
  "feature_collection": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": { "type": "Point", "coordinates": [46.6753, 24.7136] },
        "properties": { "id": "pt-1" }
      }
    ]
  }
}
'@
curl.exe -sS -X POST "$env:BASE_URL/spatial/join/mods/nearest" -H "Content-Type: application/json" --data-binary $body
```

---

## QC / QA — `GET /qc/...`

### `GET /qc/summary`

- **What it does**: High-signal QC counters (null coords, duplicates, etc).

```powershell
curl.exe "$env:BASE_URL/qc/summary"
```

### `GET /qc/duplicates/mods-id?limit=200`

- **What it does**: Duplicate MODS IDs grouped (returns `{mods_id, count}` rows).

```powershell
curl.exe "$env:BASE_URL/qc/duplicates/mods-id?limit=200"
```

### `GET /qc/duplicates/coords?limit=200`

- **What it does**: Duplicate coordinate pairs grouped.

```powershell
curl.exe "$env:BASE_URL/qc/duplicates/coords?limit=200"
```

### `GET /qc/outliers`

- **What it does**: Rule-based outlier detector (invalid coords + optional “outside expected bbox”).
- **Optional bbox params**: `expected_min_lon`, `expected_min_lat`, `expected_max_lon`, `expected_max_lat`

```powershell
curl.exe "$env:BASE_URL/qc/outliers?limit=200"
```

```powershell
curl.exe "$env:BASE_URL/qc/outliers?limit=200&expected_min_lon=34&expected_min_lat=16&expected_max_lon=56&expected_max_lat=33"
```

---

## Exports — `GET /export/...`

### `GET /export/geojson`

- **What it does**: Downloads a GeoJSON FeatureCollection.
- **Filters**: `commodity`, `region`, `occurrence_type`, `exploration_status`, and optional radial filter: `lat`, `lon`, `radius_km`

```powershell
# Save to disk
curl.exe -L "$env:BASE_URL/export/geojson?commodity=Gold&region=Riyadh&limit=500" -o mods_export.geojson
```

### `GET /export/csv`

- **What it does**: Downloads CSV (supports `stream=true` for large downloads).

```powershell
curl.exe -L "$env:BASE_URL/export/csv?commodity=Gold&limit=5000" -o mods_export.csv
```

```powershell
curl.exe -L "$env:BASE_URL/export/csv?commodity=Gold&limit=5000&stream=true" -o mods_export_stream.csv
```

---

## OGC API Features — `GET /ogc...`

### `GET /ogc`

- **What it does**: OGC API Features landing page (JSON).

```powershell
curl.exe "$env:BASE_URL/ogc"
```

### `GET /ogc/conformance`

- **What it does**: Conformance declarations (QGIS uses this).

```powershell
curl.exe "$env:BASE_URL/ogc/conformance"
```

### `GET /ogc/collections`

- **What it does**: Lists collections (currently includes `mods_occurrences`).

```powershell
curl.exe "$env:BASE_URL/ogc/collections"
```

### `GET /ogc/collections/mods_occurrences/items`

- **What it does**: Returns features (GeoJSON FeatureCollection-like) with pagination links.
- **Query**: `bbox=minLon,minLat,maxLon,maxLat`, `limit`, `offset` (or `startindex`), plus filters `commodity`, `region`, `occurrence_type`, `exploration_status`.

```powershell
curl.exe "$env:BASE_URL/ogc/collections/mods_occurrences/items?limit=100&offset=0&commodity=Gold"
```

### `GET /ogc/collections/mods_occurrences/items/{item_id}`

- **What it does**: Fetch one feature by numeric `item_id` (DB row id).

```powershell
curl.exe "$env:BASE_URL/ogc/collections/mods_occurrences/items/1"
```

---

## Vector tiles (MVT) — `GET /tiles/mvt/{z}/{x}/{y}.pbf`

- **What it does**: Returns Mapbox Vector Tiles for high-performance map viewing (binary `.pbf`).
- **Filters**: `commodity`, `region`, `occurrence_type`, `exploration_status`
- **Notes**: Save to disk or load directly in QGIS as a Vector Tile source.

```powershell
curl.exe -L "$env:BASE_URL/tiles/mvt/6/35/24.pbf?layer=mods_occurrences&commodity=Gold" -o tile.pbf
```

---

## QGIS helpers — `GET /qgis/...`

### `GET /qgis/connection`

- **What it does**: Returns PostGIS connection parameters for QGIS (password omitted unless `QGIS_EXPOSE_PASSWORD=1`).

```powershell
curl.exe "$env:BASE_URL/qgis/connection"
```

### `GET /qgis/sql-examples`

- **What it does**: Returns ready-to-copy SQL snippets for QGIS workflows.

```powershell
curl.exe "$env:BASE_URL/qgis/sql-examples"
```

---

## Files / formats — `GET /files/formats`, `POST /files/parse`

### `GET /files/formats`

- **What it does**: Lists supported upload formats and whether optional GDAL stack is installed.

```powershell
curl.exe "$env:BASE_URL/files/formats"
```

### `POST /files/parse`

- **What it does**: Upload a geospatial file and get it normalized as a GeoJSON FeatureCollection + union geometry.

```powershell
curl.exe -sS -X POST "$env:BASE_URL/files/parse" -F "file=@demo_inputs\aoi.geojson"
```

---

## Rasters (optional) — `POST /rasters/...`, `GET /jobs/...`

Raster endpoints require optional dependencies (see `requirements-raster.txt`). If raster dependencies aren’t installed, you’ll typically get a 400 with an install hint.

### `GET /rasters/formats`

```powershell
curl.exe "$env:BASE_URL/rasters/formats"
```

### `POST /rasters/upload`

- **What it does**: Uploads a raster and starts a background job that reads metadata.
- **Returns**: `job_id`, plus `status_url` you can poll.

```powershell
curl.exe -sS -X POST "$env:BASE_URL/rasters/upload" -F "file=@demo_inputs\demo.tif"
```

### `GET /jobs/{job_id}`

- **What it does**: Polls background job status/result.

```powershell
$job = "replace-with-job-id"
curl.exe "$env:BASE_URL/jobs/$job"
```

### `GET /rasters/{raster_id}/tiles/{z}/{x}/{y}.png`

- **What it does**: XYZ raster tile (PNG). Useful as a QGIS XYZ tile layer.

```powershell
$rid = "replace-with-raster-id-folder-name"
curl.exe -L "$env:BASE_URL/rasters/$rid/tiles/6/35/24.png?band=1" -o raster_tile.png
```

### `GET /rasters/{raster_id}/value?lon=...&lat=...&band=1`

- **What it does**: Sample a raster value at a lon/lat (EPSG:4326).

```powershell
$rid = "replace-with-raster-id-folder-name"
curl.exe "$env:BASE_URL/rasters/$rid/value?lon=46.6753&lat=24.7136&band=1"
```

### `POST /rasters/{raster_id}/zonal-stats`

- **What it does**: Compute zonal statistics for a polygon/geometry over the raster.

**Request body (JSON):**

```json
{
  "band": 1,
  "geometry": { "type": "Polygon", "coordinates": [[[46.0, 24.0], [47.0, 24.0], [47.0, 25.0], [46.0, 25.0], [46.0, 24.0]]] }
}
```

```powershell
$rid = "replace-with-raster-id-folder-name"
$body = @'
{
  "band": 1,
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[46.0,24.0],[47.0,24.0],[47.0,25.0],[46.0,25.0],[46.0,24.0]]]
  }
}
'@
curl.exe -sS -X POST "$env:BASE_URL/rasters/$rid/zonal-stats" -H "Content-Type: application/json" --data-binary $body
```

---

## Ingestion (disabled by default) — `POST /ingest/mods-csv`

### `POST /ingest/mods-csv`

- **What it does**: Upload a MODS-format CSV and load it into PostGIS.
- **Important**: This endpoint is **disabled unless** `INGEST_ENABLE=1` is set in the API environment.
- **Options**:
  - `replace_existing` (default true)
  - `save_as_mods_csv` (default true) — writes `MODS.csv` on disk
  - `rebuild_vectorstore` (default false) — starts embeddings rebuild in background

```powershell
curl.exe -sS -X POST "$env:BASE_URL/ingest/mods-csv?replace_existing=true&save_as_mods_csv=true&rebuild_vectorstore=false" -F "file=@MODS.csv;type=text/csv"
```

---

## Common failure modes (what they mean)

- **403 Forbidden**: Feature gated by governance. In strict mode, you may need `*_ENABLE=1` for specific features.
- **400 Bad Request**: Invalid geometry, missing parameters, or optional dependencies not installed (raster/gdal).
- **500 Internal Server Error**: Server misconfiguration (e.g., missing `DATABASE_URL`) or unexpected runtime error.

