from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.schemas import RasterZonalStatsRequest, RasterZonalStatsResponse
from app.services.governance import audit_log, feature_enabled
from app.services.job_service import create_job, set_job_status
from app.services.raster_service import (
    save_raster_bytes,
    read_raster_metadata,
    sample_raster_value,
    render_tile_png,
    rasterio_available,
    RASTERS_DIR,
)


router = APIRouter(prefix="/rasters", tags=["rasters"])


def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


def _job_background_compute_metadata(job_id: str, raster_path: Path) -> None:
    db = SessionLocal()
    try:
        set_job_status(db, job_id, "running", progress=10, message="Reading raster metadata...")
        meta = read_raster_metadata(raster_path)
        set_job_status(db, job_id, "succeeded", progress=100, message="Done", result={"path": str(raster_path), "metadata": meta})
    except Exception as e:
        set_job_status(db, job_id, "failed", progress=100, message="Failed", error=str(e))
    finally:
        db.close()


@router.get("/formats")
async def raster_formats() -> Dict[str, Any]:
    return {
        "rasterio_available": rasterio_available(),
        "supported_uploads": ["tif", "tiff", "cog(tif)"],
        "notes": [
            "Install optional raster stack with requirements-raster.txt to enable metadata and sampling.",
        ],
    }


@router.post("/upload")
async def upload_raster(
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    if not feature_enabled("rasters"):
        raise HTTPException(status_code=403, detail="Raster endpoints are disabled by data governance policy.")

    job = create_job(db, "raster_upload", message=f"Upload: {file.filename}")
    data = await file.read()
    path = save_raster_bytes(job.id, file.filename or "raster.tif", data)

    audit_log("rasters_upload", {"job_id": job.id, "filename": file.filename, "bytes": len(data)})
    background.add_task(_job_background_compute_metadata, job.id, path)

    return {"job_id": job.id, "status_url": f"/jobs/{job.id}", "raster_path": str(path)}


@router.get("/{raster_id}/download")
async def download_raster(raster_id: str) -> FileResponse:
    if not feature_enabled("rasters"):
        raise HTTPException(status_code=403, detail="Raster endpoints are disabled by data governance policy.")

    d = RASTERS_DIR / raster_id
    if not d.exists():
        raise HTTPException(status_code=404, detail="Raster not found")
    # pick first file
    files = [p for p in d.iterdir() if p.is_file()]
    if not files:
        raise HTTPException(status_code=404, detail="Raster file missing")
    audit_log("rasters_download", {"raster_id": raster_id, "filename": files[0].name})
    return FileResponse(str(files[0]), filename=files[0].name)


@router.get("/{raster_id}/value")
async def raster_value(
    raster_id: str,
    lon: float = Query(...),
    lat: float = Query(...),
    band: int = Query(1, ge=1),
) -> Dict[str, Any]:
    if not feature_enabled("rasters"):
        raise HTTPException(status_code=403, detail="Raster endpoints are disabled by data governance policy.")

    d = RASTERS_DIR / raster_id
    files = [p for p in d.iterdir() if p.is_file()] if d.exists() else []
    if not files:
        raise HTTPException(status_code=404, detail="Raster not found")

    try:
        v = sample_raster_value(files[0], lon=lon, lat=lat, band=band)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    audit_log("rasters_value", {"raster_id": raster_id, "lon": lon, "lat": lat, "band": band, "has_value": v is not None})
    return {"raster_id": raster_id, "lon": lon, "lat": lat, "band": band, "value": v}


@router.get("/{raster_id}/tiles/{z}/{x}/{y}.png")
async def raster_tile(
    raster_id: str,
    z: int,
    x: int,
    y: int,
    band: int = Query(1, ge=1),
) -> Response:
    """
    XYZ raster tiles (PNG). Suitable for QGIS XYZ tile layer.
    Requires optional raster dependencies (rasterio + pillow).
    """
    if not feature_enabled("rasters"):
        raise HTTPException(status_code=403, detail="Raster endpoints are disabled by data governance policy.")

    d = RASTERS_DIR / raster_id
    files = [p for p in d.iterdir() if p.is_file()] if d.exists() else []
    if not files:
        raise HTTPException(status_code=404, detail="Raster not found")

    try:
        png = render_tile_png(files[0], z=z, x=x, y=y, band=band)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    audit_log("rasters_tile", {"raster_id": raster_id, "z": z, "x": x, "y": y, "band": band, "bytes": len(png)})
    return Response(content=png, media_type="image/png")


@router.post("/{raster_id}/zonal-stats", response_model=RasterZonalStatsResponse)
async def raster_zonal_stats(
    raster_id: str,
    req: RasterZonalStatsRequest,
):
    """
    Zonal statistics for a polygon/geometry over a raster.
    Geometry is assumed EPSG:4326 and will be reprojected to the raster CRS if needed.
    Requires optional raster dependencies (rasterio + numpy).
    """
    if not feature_enabled("rasters"):
        raise HTTPException(status_code=403, detail="Raster endpoints are disabled by data governance policy.")

    d = RASTERS_DIR / raster_id
    files = [p for p in d.iterdir() if p.is_file()] if d.exists() else []
    if not files:
        raise HTTPException(status_code=404, detail="Raster not found")
    path = files[0]

    if not isinstance(req.geometry, dict) or "type" not in req.geometry:
        raise HTTPException(status_code=400, detail="geometry must be a GeoJSON geometry object")

    try:
        import numpy as np
        import rasterio
        from rasterio.mask import mask
        from rasterio.warp import transform_geom
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=(
                "Zonal stats require raster dependencies. Install with: pip install -r requirements-raster.txt "
                "(on Windows, Conda is often easiest)."
            ),
        ) from e

    with rasterio.open(path) as ds:
        geom = req.geometry
        if ds.crs and str(ds.crs).upper() not in ("EPSG:4326", "WGS84"):
            try:
                geom = transform_geom("EPSG:4326", ds.crs, geom, precision=6)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to reproject geometry to raster CRS: {e}")

        try:
            out, _ = mask(ds, [geom], crop=True, filled=False)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to mask raster: {e}")

        b = int(req.band)
        if b < 1 or b > ds.count:
            raise HTTPException(status_code=400, detail=f"Invalid band={b}. Raster has {ds.count} band(s).")

        arr = out[b - 1]
        # arr is a masked array if filled=False; handle robustly
        try:
            data = np.asarray(arr)
            mask_arr = np.ma.getmaskarray(arr)
            valid = data[~mask_arr]
        except Exception:
            valid = np.array([])

        if valid.size == 0:
            stats: Dict[str, Any] = {"count": 0, "min": None, "max": None, "mean": None, "std": None}
        else:
            stats = {
                "count": int(valid.size),
                "min": float(np.min(valid)),
                "max": float(np.max(valid)),
                "mean": float(np.mean(valid)),
                "std": float(np.std(valid)),
            }

    audit_log("rasters_zonal_stats", {"raster_id": raster_id, "band": int(req.band), "count": stats.get("count")})
    return RasterZonalStatsResponse(raster_id=raster_id, band=int(req.band), stats=stats)

