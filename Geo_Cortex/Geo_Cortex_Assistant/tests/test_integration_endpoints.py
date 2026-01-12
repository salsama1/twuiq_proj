from __future__ import annotations

import os
from typing import Any, Dict, Optional

import pytest
import requests


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT_SEC = float(os.getenv("TEST_TIMEOUT_SEC", "15"))


def _req(method: str, path: str, json_body: Optional[Dict[str, Any]] = None) -> requests.Response:
    return requests.request(method, f"{BASE_URL}{path}", json=json_body, timeout=TIMEOUT_SEC)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/health"),
        ("GET", "/version"),
        ("GET", "/meta/regions"),
        ("GET", "/meta/commodities"),
        ("GET", "/occurrences/mods/search?commodity=Gold&limit=3"),
        ("GET", "/occurrences/mods/bbox?min_lat=16&min_lon=34&max_lat=33&max_lon=56&limit=3"),
        ("GET", "/occurrences/mods/nearest?lat=24.7136&lon=46.6753&limit=3"),
        ("GET", "/export/geojson?commodity=Gold&limit=3"),
        ("GET", "/export/csv?commodity=Gold&limit=10"),
        ("GET", "/ogc"),
        ("GET", "/ogc/collections/mods_occurrences/items?limit=2"),
        ("GET", "/qc/summary"),
        ("GET", "/qc/duplicates/mods-id?limit=5"),
        ("GET", "/qc/duplicates/coords?limit=5"),
        ("GET", "/qc/outliers?limit=5"),
        ("GET", "/qgis/sql-examples"),
        ("GET", "/qgis/connection"),
        ("GET", "/tiles/mvt/6/36/23.pbf"),
        ("GET", "/rasters/formats"),
    ],
)
def test_basic_endpoints(method: str, path: str):
    r = _req(method, path)
    assert 200 <= r.status_code < 300, (path, r.status_code, r.text[:500])

    if path.endswith(".pbf"):
        ct = (r.headers.get("content-type") or "").lower()
        assert "mapbox-vector-tile" in ct

    if path.startswith("/ogc/collections/") and path.endswith("/items?limit=2"):
        j = r.json()
        assert j.get("type") == "FeatureCollection"


def test_advanced_polygon_query():
    poly = {
        "type": "Polygon",
        "coordinates": [[[46.0, 24.0], [47.5, 24.0], [47.5, 25.5], [46.0, 25.5], [46.0, 24.0]]],
    }
    r = _req("POST", "/advanced/mods", {"polygon": poly, "limit": 3, "return_geojson": True})
    assert 200 <= r.status_code < 300, r.text[:500]
    j = r.json()
    assert "applied" in j


def test_agent_fast_path():
    # Avoid relying on LLM by using fast-path query pattern
    r = _req("POST", "/agent/", {"query": "show gold mines in riyadh", "max_steps": 1})
    assert 200 <= r.status_code < 300, r.text[:500]
    j = r.json()
    assert "response" in j


def test_agent_workflow_endpoint():
    r = _req("POST", "/agent/workflow", {"query": "Run QC summary", "max_steps": 3, "use_llm": False})
    assert 200 <= r.status_code < 300, r.text[:500]
    j = r.json()
    assert "plan" in j


def test_spatial_intersects():
    poly = {
        "type": "Polygon",
        "coordinates": [[[46.0, 24.0], [47.0, 24.0], [47.0, 25.0], [46.0, 25.0], [46.0, 24.0]]],
    }
    r = _req(
        "POST",
        "/spatial/query",
        {"op": "intersects", "geometry": poly, "limit": 3, "return_geojson": True},
    )
    assert 200 <= r.status_code < 300, r.text[:500]
    j = r.json()
    assert "occurrences" in j


def test_spatial_buffer():
    r = _req(
        "POST",
        "/spatial/buffer",
        {"geometry": {"type": "Point", "coordinates": [46.6753, 24.7136]}, "distance_m": 10000},
    )
    assert 200 <= r.status_code < 300, r.text[:500]
    j = r.json()
    assert "geojson_geometry" in j


def test_spatial_nearest():
    r = _req(
        "POST",
        "/spatial/nearest",
        {"geometry": {"type": "Point", "coordinates": [46.6753, 24.7136]}, "limit": 3},
    )
    assert 200 <= r.status_code < 300, r.text[:500]
    j = r.json()
    assert "results" in j


def test_files_parse_geojson():
    sample_geojson = b'{\"type\":\"FeatureCollection\",\"features\":[{\"type\":\"Feature\",\"geometry\":{\"type\":\"Point\",\"coordinates\":[46.6753,24.7136]},\"properties\":{\"name\":\"p1\"}}]}'
    files = {"file": ("sample.geojson", sample_geojson, "application/geo+json")}
    r = requests.post(f"{BASE_URL}/files/parse", files=files, timeout=TIMEOUT_SEC)
    assert 200 <= r.status_code < 300, r.text[:500]
    j = r.json()
    assert j.get("feature_collection", {}).get("type") == "FeatureCollection"


