from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any, Dict, Optional


BASE_DIR = Path(__file__).resolve().parents[2]
RASTERS_DIR = BASE_DIR / "data" / "rasters"
RASTERS_DIR.mkdir(parents=True, exist_ok=True)


def rasterio_available() -> bool:
    try:
        import rasterio  # noqa: F401

        return True
    except Exception:
        return False


def save_raster_bytes(raster_id: str, filename: str, data: bytes) -> Path:
    safe_name = os.path.basename(filename or "raster.tif")
    out_dir = RASTERS_DIR / raster_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / safe_name
    out_path.write_bytes(data)
    return out_path


def read_raster_metadata(path: Path) -> Dict[str, Any]:
    try:
        import rasterio
    except Exception as e:
        raise RuntimeError(
            "Raster support requires optional dependencies. Install with: pip install -r requirements-raster.txt "
            "(on Windows, Conda is often easiest)."
        ) from e

    with rasterio.open(path) as ds:
        return {
            "driver": ds.driver,
            "width": ds.width,
            "height": ds.height,
            "count": ds.count,
            "crs": str(ds.crs) if ds.crs else None,
            "bounds": [ds.bounds.left, ds.bounds.bottom, ds.bounds.right, ds.bounds.top],
            "dtype": str(ds.dtypes[0]) if ds.dtypes else None,
            "nodata": ds.nodata,
        }


def sample_raster_value(path: Path, lon: float, lat: float, band: int = 1) -> Optional[float]:
    try:
        import rasterio
    except Exception as e:
        raise RuntimeError(
            "Raster support requires optional dependencies. Install with: pip install -r requirements-raster.txt "
            "(on Windows, Conda is often easiest)."
        ) from e

    with rasterio.open(path) as ds:
        if ds.crs and str(ds.crs).upper() not in ("EPSG:4326", "WGS84"):
            # Minimal: require EPSG:4326 for sampling to keep this lightweight.
            # (Next step would be reprojection via pyproj.)
            raise RuntimeError("Raster CRS is not EPSG:4326; reprojection not implemented yet.")
        rowcol = ds.index(lon, lat)
        val = ds.read(band, window=((rowcol[0], rowcol[0] + 1), (rowcol[1], rowcol[1] + 1)))
        if val.size == 0:
            return None
        v = float(val.flatten()[0])
        if ds.nodata is not None and v == float(ds.nodata):
            return None
        return v


def _tile_bounds_3857(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    # WebMercator bounds in meters for XYZ tile
    origin = 20037508.342789244
    n = 2 ** int(z)
    res = (2 * origin) / (256 * n)
    minx = x * 256 * res - origin
    maxx = (x + 1) * 256 * res - origin
    maxy = origin - y * 256 * res
    miny = origin - (y + 1) * 256 * res
    return minx, miny, maxx, maxy


def render_tile_png(path: Path, z: int, x: int, y: int, band: int = 1) -> bytes:
    """
    Render a 256x256 PNG XYZ tile from a raster.
    Output CRS is EPSG:3857 tile space.
    """
    try:
        import numpy as np
        import rasterio
        from rasterio.warp import reproject, Resampling
        from rasterio.transform import from_bounds
        from PIL import Image
    except Exception as e:
        raise RuntimeError(
            "Raster tile rendering requires optional dependencies. Install with: pip install -r requirements-raster.txt "
            "(on Windows, Conda is often easiest)."
        ) from e

    tile_size = 256
    minx, miny, maxx, maxy = _tile_bounds_3857(int(z), int(x), int(y))
    dst_transform = from_bounds(minx, miny, maxx, maxy, tile_size, tile_size)

    with rasterio.open(path) as ds:
        if ds.count >= 3:
            out = np.zeros((3, tile_size, tile_size), dtype=np.uint8)
            for i in range(3):
                reproject(
                    source=rasterio.band(ds, i + 1),
                    destination=out[i],
                    src_transform=ds.transform,
                    src_crs=ds.crs,
                    dst_transform=dst_transform,
                    dst_crs="EPSG:3857",
                    resampling=Resampling.bilinear,
                )
            img = Image.fromarray(np.transpose(out, (1, 2, 0)), mode="RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

        # Single-band render as grayscale
        dest = np.zeros((tile_size, tile_size), dtype=np.float32)
        reproject(
            source=rasterio.band(ds, band),
            destination=dest,
            src_transform=ds.transform,
            src_crs=ds.crs,
            dst_transform=dst_transform,
            dst_crs="EPSG:3857",
            resampling=Resampling.bilinear,
        )
        # Normalize to 0..255
        finite = dest[np.isfinite(dest)]
        if finite.size == 0:
            arr8 = np.zeros((tile_size, tile_size), dtype=np.uint8)
        else:
            vmin = float(np.percentile(finite, 2))
            vmax = float(np.percentile(finite, 98))
            if vmax <= vmin:
                vmax = vmin + 1.0
            scaled = (dest - vmin) / (vmax - vmin)
            scaled = np.clip(scaled, 0.0, 1.0)
            arr8 = (scaled * 255.0).astype(np.uint8)
        img = Image.fromarray(arr8, mode="L")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

