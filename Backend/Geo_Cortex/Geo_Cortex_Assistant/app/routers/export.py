from fastapi import APIRouter, Depends
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session
from typing import Iterator, Optional
import io
import csv
import json

from app.database import SessionLocal
from app.models.dbmodels import MODSOccurrence
from geoalchemy2.functions import ST_DWithin, ST_GeogFromText
from sqlalchemy import or_
from app.services.governance import audit_log, feature_enabled, sanitize_text


router = APIRouter(prefix="/export", tags=["export"])

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


def _apply_common_filters(
    query,
    commodity: Optional[str],
    region: Optional[str],
    occurrence_type: Optional[str],
    exploration_status: Optional[str],
    lat: Optional[float],
    lon: Optional[float],
    radius_km: Optional[float],
):
    if commodity:
        query = query.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    if region:
        v = region.replace(" and ", ",").replace(" AND ", ",")
        regions = [p.strip() for p in v.split(",") if p.strip()]
        if regions:
            query = query.filter(or_(*[MODSOccurrence.admin_region.ilike(f"%{r}%") for r in regions]))
    occurrence_type = _normalize_occurrence_type(occurrence_type)
    if occurrence_type:
        query = query.filter(MODSOccurrence.occurrence_type.ilike(f"%{occurrence_type}%"))
    if exploration_status:
        query = query.filter(MODSOccurrence.exploration_status.ilike(f"%{exploration_status}%"))
    if lat is not None and lon is not None and radius_km is not None and radius_km > 0:
        point = ST_GeogFromText(f"POINT({lon} {lat})")
        query = query.filter(ST_DWithin(MODSOccurrence.geom, point, radius_km * 1000.0))
    return query


@router.get("/geojson")
async def export_geojson(
    db: Session = Depends(get_db),
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    exploration_status: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: Optional[float] = None,
    limit: int = 500,
):
    """
    Download occurrences as GeoJSON FeatureCollection (public).
    This is convenient for UI (download button) and GIS tools.
    """
    if not feature_enabled("export"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Export is disabled by data governance policy.")
    q = db.query(MODSOccurrence)
    q = _apply_common_filters(q, commodity, region, occurrence_type, exploration_status, lat, lon, radius_km)
    rows = q.limit(limit).all()

    features = []
    for occ in rows:
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

    fc = {"type": "FeatureCollection", "features": features}
    payload = json.dumps(fc, ensure_ascii=False)
    audit_log(
        "export_geojson",
        {
            "commodity": commodity,
            "region": region,
            "occurrence_type": occurrence_type,
            "exploration_status": exploration_status,
            "lat": lat,
            "lon": lon,
            "radius_km": radius_km,
            "limit": limit,
            "features": len(features),
        },
    )

    return Response(
        content=payload,
        media_type="application/geo+json",
        headers={"Content-Disposition": "attachment; filename=mods_export.geojson"},
    )


@router.get("/csv")
async def export_csv(
    db: Session = Depends(get_db),
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    exploration_status: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: Optional[float] = None,
    limit: int = 5000,
    stream: bool = False,
):
    """
    Download occurrences as CSV (public).
    """
    if not feature_enabled("export"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Export is disabled by data governance policy.")
    q = db.query(MODSOccurrence)
    q = _apply_common_filters(q, commodity, region, occurrence_type, exploration_status, lat, lon, radius_km)
    q = q.limit(limit)

    headers = [
        "id",
        "mods_id",
        "english_name",
        "arabic_name",
        "major_commodity",
        "admin_region",
        "occurrence_type",
        "exploration_status",
        "occurrence_importance",
        "latitude",
        "longitude",
    ]

    if stream:
        def gen() -> Iterator[bytes]:
            # UTF-8 BOM so Excel renders Arabic correctly.
            yield "\ufeff".encode("utf-8")
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(headers)
            yield sanitize_text(buf.getvalue()).encode("utf-8")
            buf.seek(0)
            buf.truncate(0)

            for occ in q.yield_per(500):
                w.writerow(
                    [
                        occ.id,
                        occ.mods_id,
                        occ.english_name,
                        occ.arabic_name,
                        occ.major_commodity,
                        occ.admin_region,
                        occ.occurrence_type,
                        occ.exploration_status,
                        occ.occurrence_importance,
                        occ.latitude,
                        occ.longitude,
                    ]
                )
                yield sanitize_text(buf.getvalue()).encode("utf-8")
                buf.seek(0)
                buf.truncate(0)

        audit_log(
            "export_csv_stream",
            {
                "commodity": commodity,
                "region": region,
                "occurrence_type": occurrence_type,
                "exploration_status": exploration_status,
                "lat": lat,
                "lon": lon,
                "radius_km": radius_km,
                "limit": limit,
            },
        )
        return StreamingResponse(
            gen(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=mods_export.csv"},
        )

    rows = q.all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for occ in rows:
        writer.writerow(
            [
                occ.id,
                occ.mods_id,
                occ.english_name,
                occ.arabic_name,
                occ.major_commodity,
                occ.admin_region,
                occ.occurrence_type,
                occ.exploration_status,
                occ.occurrence_importance,
                occ.latitude,
                occ.longitude,
            ]
        )

    # Add UTF-8 BOM so Excel renders Arabic correctly.
    csv_text = "\ufeff" + buf.getvalue()
    audit_log(
        "export_csv",
        {
            "commodity": commodity,
            "region": region,
            "occurrence_type": occurrence_type,
            "exploration_status": exploration_status,
            "lat": lat,
            "lon": lon,
            "radius_km": radius_km,
            "limit": limit,
            "rows": len(rows),
            "bytes": len(csv_text.encode("utf-8")),
        },
    )

    return Response(
        content=sanitize_text(csv_text),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=mods_export.csv"},
    )

