from __future__ import annotations

import os

import requests


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT_SEC = float(os.getenv("TEST_TIMEOUT_SEC", "15"))


def test_files_formats_endpoint():
    r = requests.get(f"{BASE_URL}/files/formats", timeout=TIMEOUT_SEC)
    assert 200 <= r.status_code < 300
    j = r.json()
    assert "pure_python" in j and "gdal_optional" in j and "gdal_available" in j


def test_files_parse_gpkg_fails_safely_without_valid_file():
    # We don't ship a real GPKG fixture. The goal is: no 500s.
    dummy = b"not a real gpkg"
    files = {"file": ("dummy.gpkg", dummy, "application/geopackage+sqlite3")}
    r = requests.post(f"{BASE_URL}/files/parse", files=files, timeout=TIMEOUT_SEC)
    assert r.status_code in (400, 415)
