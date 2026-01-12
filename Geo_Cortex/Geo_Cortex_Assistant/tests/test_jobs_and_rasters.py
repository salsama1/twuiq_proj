from __future__ import annotations

import os
import time

import requests


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT_SEC = float(os.getenv("TEST_TIMEOUT_SEC", "15"))


def test_raster_upload_creates_job_and_job_endpoint_works():
    dummy_tif = b"II*\x00"  # not a real tiff; should still create job record
    files = {"file": ("dummy.tif", dummy_tif, "image/tiff")}
    r = requests.post(f"{BASE_URL}/rasters/upload", files=files, timeout=TIMEOUT_SEC)
    assert 200 <= r.status_code < 300, r.text[:500]
    job_id = r.json().get("job_id")
    assert job_id

    j = requests.get(f"{BASE_URL}/jobs/{job_id}", timeout=TIMEOUT_SEC)
    assert 200 <= j.status_code < 300, j.text[:500]
    payload = j.json()
    assert payload["id"] == job_id
    assert payload["type"] == "raster_upload"
    assert payload["status"] in ("pending", "running", "succeeded", "failed")

    # Wait briefly; it may fail if rasterio isn't installed, but must not hang.
    for _ in range(10):
        jj = requests.get(f"{BASE_URL}/jobs/{job_id}", timeout=TIMEOUT_SEC).json()
        if jj["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.2)


def test_raster_tile_endpoint_exists_returns_404_for_missing_raster():
    r = requests.get(f"{BASE_URL}/rasters/does-not-exist/tiles/0/0/0.png", timeout=TIMEOUT_SEC)
    assert r.status_code == 404
