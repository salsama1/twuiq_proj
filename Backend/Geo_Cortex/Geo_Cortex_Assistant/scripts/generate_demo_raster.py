from __future__ import annotations

r"""
Generate a tiny GeoTIFF demo file for /rasters/* endpoints.

Why a generator script?
- GeoTIFF is binary; keeping it generated avoids committing binary blobs.
- Ensures the raster is valid for rasterio-based endpoints (tiles/value/zonal-stats).

Usage (PowerShell):
  .\\.venv\\Scripts\\python scripts\\generate_demo_raster.py
"""

import os
from pathlib import Path


def main() -> int:
    try:
        import numpy as np
        import rasterio
        from rasterio.transform import from_origin
    except Exception as e:
        raise SystemExit(
            "Missing raster dependencies. Install them first:\n"
            "  .\\.venv\\Scripts\\python -m pip install -r requirements-raster.txt\n"
            f"\nOriginal error: {e}"
        )

    # Windows gotcha:
    # Some PostGIS/PostgreSQL installs ship an older PROJ database and set PROJ_LIB,
    # which can break rasterio's CRS parsing ("DATABASE.LAYOUT.VERSION.MINOR ...").
    # Prefer rasterio's bundled proj.db when available.
    try:
        import rasterio as _rio  # type: ignore

        wheel_proj = Path(_rio.__file__).resolve().parent / "proj_data"
        if wheel_proj.exists():
            os.environ["PROJ_LIB"] = str(wheel_proj)
    except Exception:
        pass

    base_dir = Path(__file__).resolve().parents[1]
    out_path = base_dir / "demo_inputs" / "demo.tif"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 10x10 float raster with a simple gradient.
    arr = (np.arange(100, dtype=np.float32).reshape((10, 10)))

    # Geo-reference: upper-left at (44E, 26N), pixel size 0.1 degrees.
    transform = from_origin(44.0, 26.0, 0.1, 0.1)

    profile = {
        "driver": "GTiff",
        "height": arr.shape[0],
        "width": arr.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
    }

    with rasterio.open(out_path, "w", **profile) as ds:
        ds.write(arr, 1)

    print(f"Wrote demo raster: {out_path}")
    print("Extent (approx): lon=[44.0..45.0], lat=[25.0..26.0] (EPSG:4326)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

