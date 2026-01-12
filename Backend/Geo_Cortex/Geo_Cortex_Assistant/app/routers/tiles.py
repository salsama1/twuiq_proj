from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.governance import audit_log, feature_enabled


router = APIRouter(prefix="/tiles", tags=["tiles"])


def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


@router.get("/mvt/{z}/{x}/{y}.pbf")
async def mvt_mods_occurrences(
    z: int,
    x: int,
    y: int,
    db: Session = Depends(get_db),
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    exploration_status: Optional[str] = None,
    limit: int = Query(50000, ge=1, le=200000),
    layer: str = Query("mods_occurrences"),
) -> Response:
    """
    Mapbox Vector Tiles (MVT) endpoint for high-performance GIS viewing.
    QGIS can consume vector tiles directly.
    """
    if not feature_enabled("tiles"):
        raise HTTPException(status_code=403, detail="Vector tiles are disabled by data governance policy.")

    # Use ST_TileEnvelope in WebMercator (EPSG:3857).
    # Our stored geom is geography; cast to geometry then transform.
    sql = text(
        """
        WITH base AS (
          SELECT
            id,
            mods_id,
            english_name,
            major_commodity,
            admin_region,
            occurrence_type,
            exploration_status,
            occurrence_importance,
            ST_Transform(geom::geometry, 3857) AS geom_3857
          FROM mods_occurrences
          WHERE geom IS NOT NULL
            AND (:commodity IS NULL OR major_commodity ILIKE :commodity_like)
            AND (:region IS NULL OR admin_region ILIKE :region_like)
            AND (:occurrence_type IS NULL OR occurrence_type ILIKE :occurrence_type_like)
            AND (:exploration_status IS NULL OR exploration_status ILIKE :exploration_status_like)
          LIMIT :row_limit
        ),
        tile AS (
          SELECT
            id,
            mods_id,
            english_name,
            major_commodity,
            admin_region,
            occurrence_type,
            exploration_status,
            occurrence_importance,
            ST_AsMVTGeom(
              geom_3857,
              ST_TileEnvelope(:z, :x, :y),
              4096,
              256,
              true
            ) AS geom
          FROM base
          WHERE geom_3857 && ST_TileEnvelope(:z, :x, :y)
        )
        SELECT COALESCE(ST_AsMVT(tile, :layer_name, 4096, 'geom'), ''::bytea) AS mvt
        FROM tile;
        """
    )

    def _like(v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return f"%{s}%" if s else None

    params = {
        "z": int(z),
        "x": int(x),
        "y": int(y),
        "layer_name": layer,
        "commodity": commodity.strip() if isinstance(commodity, str) and commodity.strip() else None,
        "region": region.strip() if isinstance(region, str) and region.strip() else None,
        "occurrence_type": occurrence_type.strip() if isinstance(occurrence_type, str) and occurrence_type.strip() else None,
        "exploration_status": exploration_status.strip() if isinstance(exploration_status, str) and exploration_status.strip() else None,
        "commodity_like": _like(commodity),
        "region_like": _like(region),
        "occurrence_type_like": _like(occurrence_type),
        "exploration_status_like": _like(exploration_status),
        "row_limit": int(limit),
    }

    mvt = db.execute(sql, params).scalar()
    if mvt is None:
        mvt = b""

    audit_log(
        "tiles_mvt",
        {
            "z": z,
            "x": x,
            "y": y,
            "layer": layer,
            "commodity": commodity,
            "region": region,
            "occurrence_type": occurrence_type,
            "exploration_status": exploration_status,
            "bytes": len(mvt),
        },
    )

    return Response(content=mvt, media_type="application/vnd.mapbox-vector-tile")

