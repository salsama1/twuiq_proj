from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func, cast
from geoalchemy2 import Geometry
from geoalchemy2.functions import ST_GeomFromGeoJSON, ST_SetSRID

from app.database import SessionLocal
from app.models.dbmodels import MODSOccurrence
from app.models.schemas import (
    AdvancedSearchRequest,
    AdvancedSearchResponse,
    OccurrenceInfo,
    GeoJSONFeatureCollection,
)
from app.services.governance import audit_log, feature_enabled


router = APIRouter(prefix="/advanced", tags=["advanced"])


def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


def _ilike_any(col, values: List[str]):
    vals = [v.strip() for v in values if v and v.strip()]
    if not vals:
        return None
    return or_(*[col.ilike(f"%{v}%") for v in vals])


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


@router.post("/mods", response_model=AdvancedSearchResponse)
async def advanced_search_mods(
    req: AdvancedSearchRequest,
    db: Session = Depends(get_db),
):
    """
    Advanced MODS query endpoint (POST) supporting:
    - multi-value filters
    - free text search
    - bbox / polygon filters (PostGIS)
    - optional GeoJSON output
    """
    if not feature_enabled("advanced"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Advanced queries are disabled by data governance policy.")
    q = db.query(MODSOccurrence)

    if req.commodities:
        expr = _ilike_any(MODSOccurrence.major_commodity, req.commodities)
        if expr is not None:
            q = q.filter(expr)
    if req.regions:
        expr = _ilike_any(MODSOccurrence.admin_region, req.regions)
        if expr is not None:
            q = q.filter(expr)
    if req.occurrence_types:
        expr = _ilike_any(MODSOccurrence.occurrence_type, req.occurrence_types)
        if expr is not None:
            q = q.filter(expr)
    if req.exploration_statuses:
        expr = _ilike_any(MODSOccurrence.exploration_status, req.exploration_statuses)
        if expr is not None:
            q = q.filter(expr)
    if req.importance:
        expr = _ilike_any(MODSOccurrence.occurrence_importance, req.importance)
        if expr is not None:
            q = q.filter(expr)

    if req.q:
        s = req.q.strip()
        if s:
            q = q.filter(
                or_(
                    MODSOccurrence.mods_id.ilike(f"%{s}%"),
                    MODSOccurrence.english_name.ilike(f"%{s}%"),
                    MODSOccurrence.arabic_name.ilike(f"%{s}%"),
                    MODSOccurrence.major_commodity.ilike(f"%{s}%"),
                    MODSOccurrence.admin_region.ilike(f"%{s}%"),
                    MODSOccurrence.occurrence_type.ilike(f"%{s}%"),
                    MODSOccurrence.exploration_status.ilike(f"%{s}%"),
                )
            )

    # Geometry filters
    if req.bbox and len(req.bbox) == 4:
        min_lon, min_lat, max_lon, max_lat = req.bbox
        q = q.filter(
            and_(
                MODSOccurrence.longitude >= min_lon,
                MODSOccurrence.longitude <= max_lon,
                MODSOccurrence.latitude >= min_lat,
                MODSOccurrence.latitude <= max_lat,
            )
        )

    if req.polygon:
        # cast geography point -> geometry point for ST_Within
        pt_geom = cast(MODSOccurrence.geom, Geometry(geometry_type="POINT", srid=4326))
        poly = ST_SetSRID(ST_GeomFromGeoJSON(json.dumps(req.polygon)), 4326)
        q = q.filter(func.ST_Within(pt_geom, poly))

    total = q.count()
    rows = q.offset(req.offset).limit(req.limit).all()

    occs = [_to_occurrence_info(o) for o in rows]
    geojson = _to_feature_collection(rows) if req.return_geojson else None

    audit_log(
        "advanced_search_mods",
        {
            "applied": req.model_dump(exclude_none=True),
            "total": int(total),
            "returned": int(len(rows)),
            "return_geojson": bool(req.return_geojson),
        },
    )

    return AdvancedSearchResponse(
        total=int(total),
        occurrences=occs,
        geojson=geojson,
        applied=req.model_dump(exclude_none=True),
    )

