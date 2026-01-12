from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import SessionLocal
from app.models.dbmodels import MODSOccurrence
from app.services.governance import audit_log, feature_enabled


router = APIRouter(prefix="/qc", tags=["qc"])


def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


def _require_qc_enabled() -> None:
    if not feature_enabled("qc"):
        raise HTTPException(status_code=403, detail="QC endpoints are disabled by data governance policy.")


@router.get("/summary")
async def qc_summary(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Quick QC summary for GIS specialists.
    """
    _require_qc_enabled()

    total = int(db.query(func.count(MODSOccurrence.id)).scalar() or 0)

    null_lon = int(db.query(func.count(MODSOccurrence.id)).filter(MODSOccurrence.longitude.is_(None)).scalar() or 0)
    null_lat = int(db.query(func.count(MODSOccurrence.id)).filter(MODSOccurrence.latitude.is_(None)).scalar() or 0)

    zero_coords = int(
        db.query(func.count(MODSOccurrence.id))
        .filter(MODSOccurrence.longitude == 0.0, MODSOccurrence.latitude == 0.0)
        .scalar()
        or 0
    )

    out_of_range = int(
        db.query(func.count(MODSOccurrence.id))
        .filter(
            MODSOccurrence.latitude.isnot(None),
            MODSOccurrence.longitude.isnot(None),
            func.abs(MODSOccurrence.latitude) > 90.0,
        )
        .scalar()
        or 0
    ) + int(
        db.query(func.count(MODSOccurrence.id))
        .filter(
            MODSOccurrence.latitude.isnot(None),
            MODSOccurrence.longitude.isnot(None),
            func.abs(MODSOccurrence.longitude) > 180.0,
        )
        .scalar()
        or 0
    )

    missing_geom = int(db.query(func.count(MODSOccurrence.id)).filter(MODSOccurrence.geom.is_(None)).scalar() or 0)

    dup_mods = int(
        db.query(func.count())
        .select_from(
            db.query(MODSOccurrence.mods_id)
            .filter(MODSOccurrence.mods_id.isnot(None), MODSOccurrence.mods_id != "")
            .group_by(MODSOccurrence.mods_id)
            .having(func.count(MODSOccurrence.id) > 1)
            .subquery()
        )
        .scalar()
        or 0
    )

    dup_coords = int(
        db.query(func.count())
        .select_from(
            db.query(MODSOccurrence.latitude, MODSOccurrence.longitude)
            .filter(MODSOccurrence.latitude.isnot(None), MODSOccurrence.longitude.isnot(None))
            .group_by(MODSOccurrence.latitude, MODSOccurrence.longitude)
            .having(func.count(MODSOccurrence.id) > 1)
            .subquery()
        )
        .scalar()
        or 0
    )

    audit_log(
        "qc_summary",
        {
            "total": total,
            "null_lat": null_lat,
            "null_lon": null_lon,
            "zero_coords": zero_coords,
            "out_of_range": out_of_range,
            "missing_geom": missing_geom,
            "duplicate_mods_id_groups": dup_mods,
            "duplicate_coord_groups": dup_coords,
        },
    )

    return {
        "total_rows": total,
        "null_latitude_rows": null_lat,
        "null_longitude_rows": null_lon,
        "zero_coord_rows": zero_coords,
        "out_of_range_rows": out_of_range,
        "missing_geom_rows": missing_geom,
        "duplicate_mods_id_groups": dup_mods,
        "duplicate_coord_groups": dup_coords,
        "notes": [
            "duplicate_*_groups counts groups with >1 rows (not total duplicate rows).",
            "out_of_range_rows counts rows outside lat/lon bounds (best-effort).",
        ],
    }


@router.get("/duplicates/mods-id")
async def qc_duplicates_mods_id(
    db: Session = Depends(get_db),
    limit: int = Query(200, ge=1, le=5000),
) -> List[Dict[str, Any]]:
    """
    Duplicate MODS IDs (grouped).
    """
    _require_qc_enabled()

    q = (
        db.query(
            MODSOccurrence.mods_id.label("mods_id"),
            func.count(MODSOccurrence.id).label("count"),
        )
        .filter(MODSOccurrence.mods_id.isnot(None), MODSOccurrence.mods_id != "")
        .group_by(MODSOccurrence.mods_id)
        .having(func.count(MODSOccurrence.id) > 1)
        .order_by(func.count(MODSOccurrence.id).desc())
        .limit(limit)
    )
    rows = [{"mods_id": m, "count": int(c)} for m, c in q.all()]

    audit_log("qc_duplicates_mods_id", {"limit": limit, "groups": len(rows)})
    return rows


@router.get("/duplicates/coords")
async def qc_duplicates_coords(
    db: Session = Depends(get_db),
    limit: int = Query(200, ge=1, le=5000),
) -> List[Dict[str, Any]]:
    """
    Duplicate coordinate pairs (lat/lon grouped).
    """
    _require_qc_enabled()

    q = (
        db.query(
            MODSOccurrence.latitude.label("latitude"),
            MODSOccurrence.longitude.label("longitude"),
            func.count(MODSOccurrence.id).label("count"),
        )
        .filter(MODSOccurrence.latitude.isnot(None), MODSOccurrence.longitude.isnot(None))
        .group_by(MODSOccurrence.latitude, MODSOccurrence.longitude)
        .having(func.count(MODSOccurrence.id) > 1)
        .order_by(func.count(MODSOccurrence.id).desc())
        .limit(limit)
    )
    rows = [{"latitude": float(lat), "longitude": float(lon), "count": int(c)} for lat, lon, c in q.all()]

    audit_log("qc_duplicates_coords", {"limit": limit, "groups": len(rows)})
    return rows


@router.get("/outliers")
async def qc_outliers(
    db: Session = Depends(get_db),
    limit: int = Query(200, ge=1, le=5000),
    # optional bbox for “expected area” checks (useful for Saudi Arabia datasets)
    expected_min_lon: Optional[float] = None,
    expected_min_lat: Optional[float] = None,
    expected_max_lon: Optional[float] = None,
    expected_max_lat: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Rule-based outlier detector.

    Returns a small sample of rows that violate rules + a breakdown of counts.
    """
    _require_qc_enabled()

    # Base invalid rules
    invalid_q = db.query(MODSOccurrence).filter(
        (MODSOccurrence.latitude.is_(None))
        | (MODSOccurrence.longitude.is_(None))
        | ((MODSOccurrence.latitude == 0.0) & (MODSOccurrence.longitude == 0.0))
        | (func.abs(MODSOccurrence.latitude) > 90.0)
        | (func.abs(MODSOccurrence.longitude) > 180.0)
    )

    # Count from subquery only (avoid cartesian product warnings)
    invalid_sub = invalid_q.with_entities(MODSOccurrence.id).subquery()
    invalid_count = int(db.query(func.count()).select_from(invalid_sub).scalar() or 0)

    expected_bbox_count = 0
    expected_bbox_enabled = (
        expected_min_lon is not None
        and expected_min_lat is not None
        and expected_max_lon is not None
        and expected_max_lat is not None
    )
    if expected_bbox_enabled:
        expected_q = db.query(MODSOccurrence).filter(
            MODSOccurrence.latitude.isnot(None),
            MODSOccurrence.longitude.isnot(None),
            ~(
                (MODSOccurrence.longitude >= expected_min_lon)
                & (MODSOccurrence.longitude <= expected_max_lon)
                & (MODSOccurrence.latitude >= expected_min_lat)
                & (MODSOccurrence.latitude <= expected_max_lat)
            ),
        )
        expected_sub = expected_q.with_entities(MODSOccurrence.id).subquery()
        expected_bbox_count = int(db.query(func.count()).select_from(expected_sub).scalar() or 0)
    else:
        expected_q = None

    # Sample rows: prioritize invalid, then expected-bbox if enabled
    sample: List[Dict[str, Any]] = []
    for occ in invalid_q.limit(limit).all():
        sample.append(
            {
                "id": occ.id,
                "mods_id": occ.mods_id,
                "english_name": occ.english_name,
                "admin_region": occ.admin_region,
                "latitude": occ.latitude,
                "longitude": occ.longitude,
                "reason": "invalid_coords",
            }
        )
        if len(sample) >= limit:
            break

    if expected_bbox_enabled and len(sample) < limit and expected_q is not None:
        remaining = limit - len(sample)
        for occ in expected_q.limit(remaining).all():
            sample.append(
                {
                    "id": occ.id,
                    "mods_id": occ.mods_id,
                    "english_name": occ.english_name,
                    "admin_region": occ.admin_region,
                    "latitude": occ.latitude,
                    "longitude": occ.longitude,
                    "reason": "outside_expected_bbox",
                }
            )

    audit_log(
        "qc_outliers",
        {
            "limit": limit,
            "invalid_count": invalid_count,
            "expected_bbox_enabled": expected_bbox_enabled,
            "expected_bbox_count": expected_bbox_count,
            "returned": len(sample),
        },
    )

    return {
        "counts": {
            "invalid_coords": invalid_count,
            "outside_expected_bbox": expected_bbox_count if expected_bbox_enabled else None,
        },
        "expected_bbox": {
            "enabled": expected_bbox_enabled,
            "min_lon": expected_min_lon,
            "min_lat": expected_min_lat,
            "max_lon": expected_max_lon,
            "max_lat": expected_max_lat,
        },
        "sample": sample,
    }

