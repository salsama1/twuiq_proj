from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List, Dict, Any

from app.database import SessionLocal
from app.models.dbmodels import MODSOccurrence


router = APIRouter(prefix="/stats", tags=["stats"])

_IGNORE_OCCURRENCE_TYPE_VALUES = {"occurrence", "occurrences", "all", "any", "none", "null"}


def _normalize_occurrence_type(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    if v.lower() in _IGNORE_OCCURRENCE_TYPE_VALUES:
        return None
    return v


def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


@router.get("/by-region")
async def stats_by_region(
    db: Session = Depends(get_db),
    commodity: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Counts grouped by admin_region (public).
    """
    q = db.query(
        MODSOccurrence.admin_region.label("admin_region"),
        func.count(MODSOccurrence.id).label("count"),
    )
    if commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    occurrence_type = _normalize_occurrence_type(occurrence_type)
    if occurrence_type:
        q = q.filter(MODSOccurrence.occurrence_type.ilike(f"%{occurrence_type}%"))
    q = q.group_by(MODSOccurrence.admin_region).order_by(func.count(MODSOccurrence.id).desc())
    return [{"admin_region": r, "count": int(c)} for r, c in q.limit(limit).all()]


@router.get("/importance")
async def importance_breakdown(
    db: Session = Depends(get_db),
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Counts grouped by occurrence_importance (public).
    """
    q = db.query(
        MODSOccurrence.occurrence_importance.label("occurrence_importance"),
        func.count(MODSOccurrence.id).label("count"),
    )
    if commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    if region:
        q = q.filter(MODSOccurrence.admin_region.ilike(f"%{region}%"))
    occurrence_type = _normalize_occurrence_type(occurrence_type)
    if occurrence_type:
        q = q.filter(MODSOccurrence.occurrence_type.ilike(f"%{occurrence_type}%"))
    q = q.group_by(MODSOccurrence.occurrence_importance).order_by(func.count(MODSOccurrence.id).desc())
    return [{"occurrence_importance": imp, "count": int(c)} for imp, c in q.all()]


@router.get("/heatmap")
async def heatmap_bins(
    db: Session = Depends(get_db),
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    bin_km: float = 25.0,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """
    Simple grid binning for map performance (public).
    Returns bins (lat, lon) + count.

    Implementation uses numeric lat/lon and approximate degrees-per-km.
    """
    bin_deg = float(bin_km) / 111.32  # ~km per degree latitude

    lon_bin = (func.floor(MODSOccurrence.longitude / bin_deg) * bin_deg).label("lon_bin")
    lat_bin = (func.floor(MODSOccurrence.latitude / bin_deg) * bin_deg).label("lat_bin")

    q = db.query(lon_bin, lat_bin, func.count(MODSOccurrence.id).label("count"))
    if commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    if region:
        q = q.filter(MODSOccurrence.admin_region.ilike(f"%{region}%"))
    occurrence_type = _normalize_occurrence_type(occurrence_type)
    if occurrence_type:
        q = q.filter(MODSOccurrence.occurrence_type.ilike(f"%{occurrence_type}%"))

    q = q.group_by(lon_bin, lat_bin).order_by(func.count(MODSOccurrence.id).desc()).limit(limit)
    rows = q.all()
    return [{"lon": float(lon), "lat": float(lat), "count": int(c)} for lon, lat, c in rows]

