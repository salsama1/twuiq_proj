from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services.governance import audit_log, feature_enabled
from app.services.geofile_service import parse_geofile, featurecollection_to_union_geometry


router = APIRouter(prefix="/files", tags=["files"])


@router.post("/parse")
async def parse_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Upload a geospatial file and return it normalized as GeoJSON FeatureCollection.
    Supported: GeoJSON, KML, GPX, WKT.
    """
    if not feature_enabled("files"):
        raise HTTPException(status_code=403, detail="File parsing is disabled by data governance policy.")

    data = await file.read()
    try:
        fc = parse_geofile(file.filename or "", file.content_type, data)
        union_geom = featurecollection_to_union_geometry(fc)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    audit_log(
        "files_parse",
        {"filename": file.filename, "content_type": file.content_type, "features": len(fc.get("features") or [])},
    )

    return {
        "type": "parsed_file",
        "filename": file.filename,
        "content_type": file.content_type,
        "feature_collection": fc,
        "union_geometry": union_geom,
    }


@router.get("/formats")
async def supported_formats() -> Dict[str, Any]:
    """
    Returns supported upload formats and whether optional GDAL stack is available.
    """
    try:
        import fiona  # noqa: F401

        gdal = True
    except Exception:
        gdal = False

    return {
        "pure_python": ["geojson", "kml", "gpx", "wkt"],
        "gdal_optional": ["gpkg", "zip(shapefile/fgdb)"],
        "gdal_available": gdal,
        "notes": [
            "If gdal_available is false, install optional dependencies with requirements-gdal.txt (Conda recommended on Windows).",
        ],
    }

