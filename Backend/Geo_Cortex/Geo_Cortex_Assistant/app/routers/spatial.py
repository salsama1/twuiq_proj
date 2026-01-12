from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, cast, text as sql_text
from geoalchemy2 import Geometry
from geoalchemy2.functions import ST_AsGeoJSON, ST_Buffer, ST_Distance, ST_GeomFromGeoJSON, ST_SetSRID, ST_Transform

from app.database import SessionLocal
from app.models.dbmodels import MODSOccurrence
from app.models.schemas import (
    OccurrenceInfo,
    GeoJSONFeatureCollection,
    SpatialBufferRequest,
    SpatialBufferResponse,
    SpatialNearestRequest,
    SpatialNearestResponse,
    SpatialQueryRequest,
    SpatialQueryResponse,
)
from app.services.governance import audit_log, feature_enabled


router = APIRouter(prefix="/spatial", tags=["spatial"])


def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


def _split_multi(value: Optional[str]) -> List[str]:
    if not value:
        return []
    v = value.strip()
    if not v:
        return []
    v = v.replace(" and ", ",").replace(" AND ", ",")
    parts = [p.strip() for p in v.split(",")]
    return [p for p in parts if p]


def _normalize_occurrence_type(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    if v.lower() in {"occurrence", "occurrences", "all", "any", "none", "null"}:
        return None
    return v


def _to_occurrence_info(occ: MODSOccurrence) -> OccurrenceInfo:
    return OccurrenceInfo(
        mods_id=occ.mods_id,
        english_name=occ.english_name,
        arabic_name=occ.arabic_name,
        major_commodity=occ.major_commodity,
        longitude=occ.longitude,
        latitude=occ.latitude,
        admin_region=occ.admin_region,
        elevation=occ.elevation,
        occurrence_type=occ.occurrence_type,
        exploration_status=occ.exploration_status,
        occurrence_importance=occ.occurrence_importance,
        description=f"{occ.major_commodity} occurrence in {occ.admin_region}",
    )


def _to_feature_collection(rows: List[MODSOccurrence]) -> GeoJSONFeatureCollection:
    features = []
    for occ in rows:
        if occ.longitude is None or occ.latitude is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [occ.longitude, occ.latitude]},
                "properties": {
                    "id": occ.id,
                    "mods_id": occ.mods_id,
                    "english_name": occ.english_name,
                    "arabic_name": occ.arabic_name,
                    "major_commodity": occ.major_commodity,
                    "admin_region": occ.admin_region,
                    "occurrence_type": occ.occurrence_type,
                    "exploration_status": occ.exploration_status,
                    "occurrence_importance": occ.occurrence_importance,
                },
            }
        )
    return GeoJSONFeatureCollection.model_validate({"type": "FeatureCollection", "features": features})


@router.post("/query", response_model=SpatialQueryResponse)
async def spatial_query(req: SpatialQueryRequest, db: Session = Depends(get_db)):
    """
    Spatial operations on MODS points using GeoJSON geometry input.

    - op=intersects: return points intersecting the given geometry
    - op=dwithin: return points within distance_m (meters) of the geometry
    """
    if not feature_enabled("spatial"):
        raise HTTPException(status_code=403, detail="Spatial operations are disabled by data governance policy.")

    if not isinstance(req.geometry, dict) or "type" not in req.geometry:
        raise HTTPException(status_code=400, detail="geometry must be a GeoJSON geometry object")

    # Input geometry in EPSG:4326
    geom_4326 = ST_SetSRID(ST_GeomFromGeoJSON(json.dumps(req.geometry)), 4326)

    q = db.query(MODSOccurrence)

    if req.commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{req.commodity}%"))
    if req.region:
        regions = _split_multi(req.region)
        if regions:
            q = q.filter(or_(*[MODSOccurrence.admin_region.ilike(f"%{r}%") for r in regions]))
    occ_type = _normalize_occurrence_type(req.occurrence_type)
    if occ_type:
        q = q.filter(MODSOccurrence.occurrence_type.ilike(f"%{occ_type}%"))
    if req.exploration_status:
        q = q.filter(MODSOccurrence.exploration_status.ilike(f"%{req.exploration_status}%"))

    # Geometry predicate
    pt_geom_4326 = cast(MODSOccurrence.geom, Geometry(geometry_type="POINT", srid=4326))

    if req.op == "intersects":
        q = q.filter(func.ST_Intersects(pt_geom_4326, geom_4326))
    elif req.op == "dwithin":
        if req.distance_m is None:
            raise HTTPException(status_code=400, detail="distance_m is required for op=dwithin")
        # Use WebMercator for meter-based buffering/dwithin.
        pt_3857 = ST_Transform(pt_geom_4326, 3857)
        geom_3857 = ST_Transform(geom_4326, 3857)
        q = q.filter(func.ST_DWithin(pt_3857, geom_3857, float(req.distance_m)))
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported op: {req.op}")

    total = int(q.count())
    rows = q.offset(req.offset).limit(req.limit).all()

    resp = SpatialQueryResponse(
        total=total,
        occurrences=[_to_occurrence_info(o) for o in rows],
        geojson=_to_feature_collection(rows) if req.return_geojson else None,
        applied=req.model_dump(exclude_none=True),
    )

    audit_log(
        "spatial_query",
        {
            "op": req.op,
            "distance_m": req.distance_m,
            "limit": req.limit,
            "offset": req.offset,
            "commodity": req.commodity,
            "region": req.region,
            "occurrence_type": req.occurrence_type,
            "exploration_status": req.exploration_status,
            "returned": len(rows),
        },
    )

    return resp


@router.post("/buffer", response_model=SpatialBufferResponse)
async def spatial_buffer(req: SpatialBufferRequest, db: Session = Depends(get_db)):
    """
    Buffer any GeoJSON geometry by distance_m (meters) and return the buffer polygon as GeoJSON.
    """
    if not feature_enabled("spatial"):
        raise HTTPException(status_code=403, detail="Spatial operations are disabled by data governance policy.")
    if not isinstance(req.geometry, dict) or "type" not in req.geometry:
        raise HTTPException(status_code=400, detail="geometry must be a GeoJSON geometry object")

    # Do buffering in WebMercator for meter units, then transform back to 4326.
    r = db.execute(
        sql_text(
            "SELECT ST_AsGeoJSON("
            "  ST_Transform("
            "    ST_Buffer("
            "      ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:g),4326),3857),"
            "      :d"
            "    ),"
            "    4326"
            "  )"
            ")"
        ),
        {"g": json.dumps(req.geometry), "d": float(req.distance_m)},
    ).first()
    if not r or not r[0]:
        raise HTTPException(status_code=500, detail="Failed to compute buffer geometry")

    geom_out: Dict[str, Any] = json.loads(r[0])

    audit_log("spatial_buffer", {"distance_m": req.distance_m})
    return SpatialBufferResponse(geojson_geometry=geom_out, applied=req.model_dump(exclude_none=True))


@router.post("/nearest", response_model=SpatialNearestResponse)
async def spatial_nearest(req: SpatialNearestRequest, db: Session = Depends(get_db)):
    """
    Find nearest MODS points to an arbitrary GeoJSON geometry.
    Distances are computed in meters using WebMercator (EPSG:3857).
    """
    if not feature_enabled("spatial"):
        raise HTTPException(status_code=403, detail="Spatial operations are disabled by data governance policy.")
    if not isinstance(req.geometry, dict) or "type" not in req.geometry:
        raise HTTPException(status_code=400, detail="geometry must be a GeoJSON geometry object")

    geom_4326 = ST_SetSRID(ST_GeomFromGeoJSON(json.dumps(req.geometry)), 4326)
    geom_3857 = ST_Transform(geom_4326, 3857)

    q = db.query(MODSOccurrence)
    if req.commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{req.commodity}%"))
    if req.region:
        regions = _split_multi(req.region)
        if regions:
            q = q.filter(or_(*[MODSOccurrence.admin_region.ilike(f"%{r}%") for r in regions]))
    occ_type = _normalize_occurrence_type(req.occurrence_type)
    if occ_type:
        q = q.filter(MODSOccurrence.occurrence_type.ilike(f"%{occ_type}%"))
    if req.exploration_status:
        q = q.filter(MODSOccurrence.exploration_status.ilike(f"%{req.exploration_status}%"))

    pt_geom_4326 = cast(MODSOccurrence.geom, Geometry(geometry_type="POINT", srid=4326))
    pt_3857 = ST_Transform(pt_geom_4326, 3857)
    dist_m = ST_Distance(pt_3857, geom_3857).label("distance_m")

    rows = q.with_entities(MODSOccurrence, dist_m).order_by(dist_m.asc()).limit(req.limit).all()

    out: List[Dict[str, Any]] = []
    for occ, d in rows:
        out.append(
            {
                "distance_m": float(d) if d is not None else None,
                "occurrence": _to_occurrence_info(occ).model_dump(),
            }
        )

    audit_log("spatial_nearest", {"limit": req.limit, "returned": len(out)})
    return SpatialNearestResponse(total_returned=len(out), results=out, applied=req.model_dump(exclude_none=True))

