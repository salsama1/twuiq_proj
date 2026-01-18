from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import SessionLocal
from app.models.dbmodels import MODSOccurrence
from app.models.schemas import OccurrenceInfo

from geoalchemy2.functions import ST_DWithin, ST_GeogFromText, ST_Distance
from app.database import IS_POSTGIS

router = APIRouter(prefix="/occurrences", tags=["occurrences"])


def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

@router.get("/mods/search", response_model=List[OccurrenceInfo])
async def search_mods_occurrences(
    db: Session = Depends(get_db),
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    # PostGIS geo filter (optional)
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: Optional[float] = None,
    limit: int = 50,
):
    """Search MODS occurrences by filters (public; no auth)."""
    query = db.query(MODSOccurrence)

    if commodity:
        query = query.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    if region:
        query = query.filter(MODSOccurrence.admin_region.ilike(f"%{region}%"))
    if occurrence_type:
        query = query.filter(MODSOccurrence.occurrence_type.ilike(f"%{occurrence_type}%"))

    if lat is not None and lon is not None and radius_km is not None:
        if not IS_POSTGIS:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Spatial search requires PostGIS (set DATABASE_URL to a PostgreSQL+PostGIS database).",
            )
        point = ST_GeogFromText(f"POINT({lon} {lat})")
        # geography distance uses meters
        query = query.filter(ST_DWithin(MODSOccurrence.geom, point, radius_km * 1000.0))

    results = query.limit(limit).all()

    return [
        OccurrenceInfo(
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
        for occ in results
    ]


@router.get("/mods/bbox", response_model=List[OccurrenceInfo])
async def bbox_mods_occurrences(
    db: Session = Depends(get_db),
    min_lat: float = -90.0,
    min_lon: float = -180.0,
    max_lat: float = 90.0,
    max_lon: float = 180.0,
    commodity: Optional[str] = None,
    limit: int = 50,
):
    """Bounding-box filter using numeric lat/lon columns (public)."""
    query = db.query(MODSOccurrence).filter(
        MODSOccurrence.latitude >= min_lat,
        MODSOccurrence.latitude <= max_lat,
        MODSOccurrence.longitude >= min_lon,
        MODSOccurrence.longitude <= max_lon,
    )
    if commodity:
        query = query.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    results = query.limit(limit).all()
    return [
        OccurrenceInfo(
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
        for occ in results
    ]


@router.get("/mods/nearest")
async def nearest_mods_occurrences(
    db: Session = Depends(get_db),
    lat: float = 0.0,
    lon: float = 0.0,
    commodity: Optional[str] = None,
    limit: int = 25,
):
    """Nearest occurrences by PostGIS distance (meters)."""
    if not IS_POSTGIS:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Nearest/spatial queries require PostGIS (set DATABASE_URL to a PostgreSQL+PostGIS database).",
        )
    point = ST_GeogFromText(f"POINT({lon} {lat})")
    dist_m = ST_Distance(MODSOccurrence.geom, point).label("distance_m")
    query = db.query(MODSOccurrence, dist_m)
    if commodity:
        query = query.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    rows = query.order_by(dist_m.asc()).limit(limit).all()
    return [
        {"distance_m": float(d) if d is not None else None, "occurrence": OccurrenceInfo(
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
        ).model_dump()}
        for occ, d in rows
    ]


@router.get("/mods/{mods_row_id}", response_model=OccurrenceInfo)
async def get_mods_occurrence(
    mods_row_id: int = Path(gt=0),
    db: Session = Depends(get_db),
):
    """Fetch a MODS occurrence by DB row id (public; no auth)."""
    occ = db.query(MODSOccurrence).filter(MODSOccurrence.id == mods_row_id).first()
    if occ is None:
        # FastAPI will serialize this as a 404 by raising; keep minimal deps
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Occurrence not found")
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
