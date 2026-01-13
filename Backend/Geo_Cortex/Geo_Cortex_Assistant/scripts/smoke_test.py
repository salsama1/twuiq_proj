from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, Optional, Tuple

import requests


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT_SEC = float(os.getenv("SMOKE_TIMEOUT_SEC", "15"))


def check(name: str, method: str, path: str, json_body: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[requests.Response]]:
    url = f"{BASE_URL}{path}"
    t0 = time.time()
    try:
        resp = requests.request(method, url, json=json_body, timeout=TIMEOUT_SEC)
        ms = int((time.time() - t0) * 1000)
        ok = 200 <= resp.status_code < 300
        print(f"{name:18} {resp.status_code:3} {ms:5}ms {path}")
        return ok, resp
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        print(f"{name:18} ERR {ms:5}ms {path} :: {e}")
        return False, None


def check_multipart(name: str, path: str, files: Dict[str, Tuple[str, bytes, str]], data: Dict[str, Any]) -> bool:
    url = f"{BASE_URL}{path}"
    t0 = time.time()
    try:
        resp = requests.post(url, files=files, data=data, timeout=TIMEOUT_SEC)
        ms = int((time.time() - t0) * 1000)
        ok = 200 <= resp.status_code < 300
        print(f"{name:18} {resp.status_code:3} {ms:5}ms {path}")
        return ok
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        print(f"{name:18} ERR {ms:5}ms {path} :: {e}")
        return False


def check_multipart_resp(name: str, path: str, files: Dict[str, Tuple[str, bytes, str]], data: Dict[str, Any]) -> Tuple[bool, Optional[requests.Response]]:
    url = f"{BASE_URL}{path}"
    t0 = time.time()
    try:
        resp = requests.post(url, files=files, data=data, timeout=TIMEOUT_SEC)
        ms = int((time.time() - t0) * 1000)
        ok = 200 <= resp.status_code < 300
        print(f"{name:18} {resp.status_code:3} {ms:5}ms {path}")
        return ok, resp
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        print(f"{name:18} ERR {ms:5}ms {path} :: {e}")
        return False, None


def wait_for_server(max_wait_sec: float = 30.0) -> bool:
    """
    When running with `uvicorn --reload`, the server may restart during edits.
    This waits for /health to become reachable before running the rest of the smoke tests.
    """
    url = f"{BASE_URL}/health"
    t0 = time.time()
    while (time.time() - t0) < max_wait_sec:
        try:
            r = requests.get(url, timeout=1.0)
            if 200 <= r.status_code < 300:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    all_ok = True
    if not wait_for_server():
        print(f"Server not reachable at {BASE_URL} (timeout). Is uvicorn running?")
        return 1

    all_ok &= check("health", "GET", "/health")[0]
    all_ok &= check("version", "GET", "/version")[0]
    all_ok &= check("meta_regions", "GET", "/meta/regions")[0]
    all_ok &= check("meta_commod", "GET", "/meta/commodities")[0]

    all_ok &= check("occ_search", "GET", "/occurrences/mods/search?commodity=Gold&limit=3")[0]
    all_ok &= check("occ_bbox", "GET", "/occurrences/mods/bbox?min_lat=16&min_lon=34&max_lat=33&max_lon=56&limit=3")[0]
    all_ok &= check("occ_nearest", "GET", "/occurrences/mods/nearest?lat=24.7136&lon=46.6753&limit=3")[0]

    poly = {
        "type": "Polygon",
        "coordinates": [[[46.0, 24.0], [47.5, 24.0], [47.5, 25.5], [46.0, 25.5], [46.0, 24.0]]],
    }
    ok, adv = check(
        "advanced_poly",
        "POST",
        "/advanced/mods",
        {"polygon": poly, "limit": 3, "return_geojson": True},
    )
    all_ok &= ok
    if adv is not None and adv.ok:
        j = adv.json()
        if "geojson" not in j:
            print("advanced_poly WARN: response missing 'geojson'")

    all_ok &= check("export_geojson", "GET", "/export/geojson?commodity=Gold&limit=3")[0]
    all_ok &= check("export_csv", "GET", "/export/csv?commodity=Gold&limit=10")[0]

    all_ok &= check("ogc_landing", "GET", "/ogc")[0]
    ok, ogc_items = check("ogc_items", "GET", "/ogc/collections/mods_occurrences/items?limit=2")
    all_ok &= ok
    if ogc_items is not None and ogc_items.ok:
        j = ogc_items.json()
        if j.get("type") != "FeatureCollection":
            print("ogc_items FAIL: expected FeatureCollection")
            all_ok = False

    all_ok &= check("qc_summary", "GET", "/qc/summary")[0]
    all_ok &= check("qc_dups_mods", "GET", "/qc/duplicates/mods-id?limit=5")[0]
    all_ok &= check("qc_dups_coord", "GET", "/qc/duplicates/coords?limit=5")[0]
    all_ok &= check("qc_outliers", "GET", "/qc/outliers?limit=5")[0]

    all_ok &= check("qgis_sql", "GET", "/qgis/sql-examples")[0]

    # /qgis/connection is allowed to be 500 if DATABASE_URL isn't set in the server env
    ok, conn = check("qgis_conn", "GET", "/qgis/connection")
    if conn is not None and conn.status_code == 500:
        print("qgis_conn INFO: 500 (expected if DATABASE_URL not set in uvicorn env)")
    else:
        all_ok &= ok

    # Agent (fast-path; avoids needing LLM)
    all_ok &= check("agent_fast", "POST", "/agent/", {"query": "show gold mines in riyadh", "max_steps": 1})[0]

    # Vector tile (may be empty, but should return 200 + correct content-type)
    ok, tile = check("tiles_mvt", "GET", "/tiles/mvt/6/36/23.pbf")
    all_ok &= ok
    if tile is not None and tile.ok:
        ct = (tile.headers.get("content-type") or "").lower()
        if "mapbox-vector-tile" not in ct:
            print(f"tiles_mvt WARN: unexpected content-type: {ct}")

    # Spatial ops (intersects)
    poly = {
        "type": "Polygon",
        "coordinates": [[[46.0, 24.0], [47.0, 24.0], [47.0, 25.0], [46.0, 25.0], [46.0, 24.0]]],
    }
    all_ok &= check(
        "spatial_int",
        "POST",
        "/spatial/query",
        {"op": "intersects", "geometry": poly, "limit": 3, "return_geojson": True},
    )[0]

    # Spatial buffer
    all_ok &= check(
        "spatial_buf",
        "POST",
        "/spatial/buffer",
        {"geometry": {"type": "Point", "coordinates": [46.6753, 24.7136]}, "distance_m": 10000},
    )[0]

    # Spatial nearest
    all_ok &= check(
        "spatial_near",
        "POST",
        "/spatial/nearest",
        {"geometry": {"type": "Point", "coordinates": [46.6753, 24.7136]}, "limit": 3},
    )[0]

    # Spatial overlay + dissolve + joins (vector GIS toolbox)
    poly_a = {"type": "Polygon", "coordinates": [[[46.0, 24.0], [47.5, 24.0], [47.5, 25.5], [46.0, 25.5], [46.0, 24.0]]]}
    poly_b = {"type": "Polygon", "coordinates": [[[47.0, 24.7], [48.2, 24.7], [48.2, 26.0], [47.0, 26.0], [47.0, 24.7]]]}
    all_ok &= check("spatial_ovl", "POST", "/spatial/overlay", {"op": "intersection", "a": poly_a, "b": poly_b})[0]

    dissolve_fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"id": 1, "group": "A"}, "geometry": {"type": "Polygon", "coordinates": [[[46.0, 24.0], [46.8, 24.0], [46.8, 24.8], [46.0, 24.8], [46.0, 24.0]]]}},
            {"type": "Feature", "properties": {"id": 2, "group": "A"}, "geometry": {"type": "Polygon", "coordinates": [[[46.6, 24.6], [47.4, 24.6], [47.4, 25.4], [46.6, 25.4], [46.6, 24.6]]]}},
            {"type": "Feature", "properties": {"id": 3, "group": "B"}, "geometry": {"type": "Polygon", "coordinates": [[[47.6, 24.2], [48.2, 24.2], [48.2, 24.8], [47.6, 24.8], [47.6, 24.2]]]}},
        ],
    }
    all_ok &= check("spatial_dis", "POST", "/spatial/dissolve", {"feature_collection": dissolve_fc, "by_property": "group"})[0]

    join_fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"id": "poly_1"}, "geometry": {"type": "Polygon", "coordinates": [[[44.0, 22.0], [45.2, 22.0], [45.2, 23.2], [44.0, 23.2], [44.0, 22.0]]]}},
            {"type": "Feature", "properties": {"id": "poly_2"}, "geometry": {"type": "Polygon", "coordinates": [[[46.0, 24.0], [47.0, 24.0], [47.0, 25.0], [46.0, 25.0], [46.0, 24.0]]]}},
        ],
    }
    all_ok &= check("join_counts", "POST", "/spatial/join/mods/counts", {"feature_collection": join_fc, "predicate": "intersects", "id_property": "id"})[0]
    all_ok &= check("join_near", "POST", "/spatial/join/mods/nearest", {"feature_collection": join_fc, "id_property": "id"})[0]

    # File parse (GeoJSON)
    sample_geojson = b'{"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point","coordinates":[46.6753,24.7136]},"properties":{"name":"p1"}}]}'
    all_ok &= check_multipart(
        "files_parse",
        "/files/parse",
        files={"file": ("sample.geojson", sample_geojson, "application/geo+json")},
        data={},
    )

    # Agent with file (fast-ish): ask for nearest to uploaded geometry
    all_ok &= check_multipart(
        "agent_file",
        "/agent/file",
        files={"file": ("sample.geojson", sample_geojson, "application/geo+json")},
        data={"query": "Find the nearest occurrences to this uploaded geometry", "max_steps": "3"},
    )

    # Workflow agent (no file)
    all_ok &= check(
        "agent_workflow",
        "POST",
        "/agent/workflow",
        {"query": "Run QC summary and tell me what it means", "max_steps": 3, "use_llm": False},
    )[0]

    # Workflow agent with file
    all_ok &= check_multipart(
        "workflow_file",
        "/agent/workflow/file",
        files={"file": ("sample.geojson", sample_geojson, "application/geo+json")},
        data={"query": "Buffer this AOI by 10 km and then find nearest occurrences", "max_steps": "5", "use_llm": "false"},
    )

    # Workflow agent: dissolve + join on uploaded FeatureCollection (offline mode)
    dissolve_fc = b'{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"id":1,"group":"A"},"geometry":{"type":"Polygon","coordinates":[[[46.0,24.0],[46.8,24.0],[46.8,24.8],[46.0,24.8],[46.0,24.0]]]}},{"type":"Feature","properties":{"id":2,"group":"A"},"geometry":{"type":"Polygon","coordinates":[[[46.6,24.6],[47.4,24.6],[47.4,25.4],[46.6,25.4],[46.6,24.6]]]}},{"type":"Feature","properties":{"id":3,"group":"B"},"geometry":{"type":"Polygon","coordinates":[[[47.6,24.2],[48.2,24.2],[48.2,24.8],[47.6,24.8],[47.6,24.2]]]}}]}'
    all_ok &= check_multipart(
        "workflow_dis",
        "/agent/workflow/file",
        files={"file": ("dissolve.geojson", dissolve_fc, "application/geo+json")},
        data={"query": "Dissolve by group and then do a spatial join count", "max_steps": "6", "use_llm": "false"},
    )

    # Rasters: upload a tiny valid GeoTIFF if rasterio is available, then test zonal stats.
    ok, r = check("rasters_formats", "GET", "/rasters/formats")
    all_ok &= ok
    raster_id = None
    try:
        import numpy as np  # noqa: F401
        import rasterio  # noqa: F401
        from rasterio.io import MemoryFile  # noqa: F401
        from rasterio.transform import from_origin  # noqa: F401

        import numpy as np
        from rasterio.io import MemoryFile
        from rasterio.transform import from_origin

        arr = (np.arange(100, dtype=np.float32).reshape((10, 10)))
        transform = from_origin(44.0, 26.0, 0.1, 0.1)  # lon, lat, pixel size
        profile = {
            "driver": "GTiff",
            "height": arr.shape[0],
            "width": arr.shape[1],
            "count": 1,
            "dtype": "float32",
            "crs": "EPSG:4326",
            "transform": transform,
        }
        with MemoryFile() as mem:
            with mem.open(**profile) as ds:
                ds.write(arr, 1)
            tif_bytes = mem.read()

        ok2, resp = check_multipart_resp(
            "rasters_upload",
            "/rasters/upload",
            files={"file": ("demo.tif", tif_bytes, "image/tiff")},
            data={},
        )
        all_ok &= ok2
        if resp is not None and resp.ok:
            raster_id = resp.json().get("job_id")
    except Exception:
        # Fallback: keep previous behavior; don't fail smoke if raster stack isn't present
        dummy_tif = b"II*\x00"
        all_ok &= check_multipart(
            "rasters_upload",
            "/rasters/upload",
            files={"file": ("dummy.tif", dummy_tif, "image/tiff")},
            data={},
        )

    if raster_id:
        # polygon covering part of the demo raster extent
        zpoly = {
            "type": "Polygon",
            "coordinates": [[[44.1, 25.1], [44.6, 25.1], [44.6, 25.6], [44.1, 25.6], [44.1, 25.1]]],
        }
        all_ok &= check(
            "zonal_stats",
            "POST",
            f"/rasters/{raster_id}/zonal-stats",
            {"geometry": zpoly, "band": 1},
        )[0]

    print("\nRESULT:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

