from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import SessionLocal
from app.models.dbmodels import MODSOccurrence
from app.services.governance import audit_log, feature_enabled


router = APIRouter(prefix="/ogc", tags=["ogc"])


def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


def _require_ogc_enabled() -> None:
    if not feature_enabled("ogc"):
        raise HTTPException(status_code=403, detail="OGC API Features is disabled by data governance policy.")


def _base_url(request: Request) -> str:
    # request.base_url includes trailing slash
    return str(request.base_url).rstrip("/")


def _parse_bbox(bbox: Optional[str]) -> Optional[Tuple[float, float, float, float]]:
    if not bbox:
        return None
    parts = [p.strip() for p in bbox.split(",") if p.strip()]
    if len(parts) < 4:
        raise HTTPException(status_code=400, detail="bbox must be 'minLon,minLat,maxLon,maxLat'")
    try:
        min_lon, min_lat, max_lon, max_lat = map(float, parts[:4])
    except Exception:
        raise HTTPException(status_code=400, detail="bbox values must be numbers")
    if min_lon > max_lon or min_lat > max_lat:
        raise HTTPException(status_code=400, detail="bbox min values must be <= max values")
    return min_lon, min_lat, max_lon, max_lat


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


def _apply_filters(
    q,
    commodity: Optional[str],
    region: Optional[str],
    occurrence_type: Optional[str],
    exploration_status: Optional[str],
    bbox: Optional[Tuple[float, float, float, float]],
):
    if commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    if region:
        regions = _split_multi(region)
        if regions:
            q = q.filter(or_(*[MODSOccurrence.admin_region.ilike(f"%{r}%") for r in regions]))
    occurrence_type = _normalize_occurrence_type(occurrence_type)
    if occurrence_type:
        q = q.filter(MODSOccurrence.occurrence_type.ilike(f"%{occurrence_type}%"))
    if exploration_status:
        q = q.filter(MODSOccurrence.exploration_status.ilike(f"%{exploration_status}%"))
    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        q = q.filter(
            MODSOccurrence.longitude >= min_lon,
            MODSOccurrence.longitude <= max_lon,
            MODSOccurrence.latitude >= min_lat,
            MODSOccurrence.latitude <= max_lat,
        )
    return q


def _feature_from_occ(occ: MODSOccurrence) -> Dict[str, Any]:
    return {
        "type": "Feature",
        "id": occ.id,
        "geometry": {"type": "Point", "coordinates": [occ.longitude, occ.latitude]},
        "properties": {
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


@router.get("")
async def landing(request: Request) -> Dict[str, Any]:
    _require_ogc_enabled()
    base = _base_url(request)
    return {
        "title": "Geo_Cortex_Assistant OGC API Features",
        "links": [
            {"rel": "self", "type": "application/json", "href": f"{base}/ogc"},
            {"rel": "conformance", "type": "application/json", "href": f"{base}/ogc/conformance"},
            {"rel": "data", "type": "application/json", "href": f"{base}/ogc/collections"},
        ],
    }


@router.get("/conformance")
async def conformance(request: Request) -> Dict[str, Any]:
    _require_ogc_enabled()
    base = _base_url(request)
    return {
        "links": [{"rel": "self", "type": "application/json", "href": f"{base}/ogc/conformance"}],
        # Minimal set that QGIS understands well
        "conformsTo": [
            "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
            "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30",
            "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
        ],
    }


@router.get("/collections")
async def collections(request: Request) -> Dict[str, Any]:
    _require_ogc_enabled()
    base = _base_url(request)
    return {
        "collections": [
            {
                "id": "mods_occurrences",
                "title": "MODS Occurrences",
                "description": "Mineral occurrence points (WGS84 / EPSG:4326).",
                "itemType": "feature",
                "crs": ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
                "links": [
                    {"rel": "self", "type": "application/json", "href": f"{base}/ogc/collections/mods_occurrences"},
                    {
                        "rel": "items",
                        "type": "application/geo+json",
                        "href": f"{base}/ogc/collections/mods_occurrences/items",
                    },
                ],
            }
        ],
        "links": [{"rel": "self", "type": "application/json", "href": f"{base}/ogc/collections"}],
    }


@router.get("/collections/mods_occurrences")
async def collection_mods_occurrences(request: Request) -> Dict[str, Any]:
    _require_ogc_enabled()
    base = _base_url(request)
    return {
        "id": "mods_occurrences",
        "title": "MODS Occurrences",
        "description": "Mineral occurrence points (WGS84 / EPSG:4326).",
        "itemType": "feature",
        "crs": ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
        "links": [
            {"rel": "self", "type": "application/json", "href": f"{base}/ogc/collections/mods_occurrences"},
            {"rel": "items", "type": "application/geo+json", "href": f"{base}/ogc/collections/mods_occurrences/items"},
        ],
    }


@router.get("/collections/mods_occurrences/items")
async def collection_items(
    request: Request,
    db: Session = Depends(get_db),
    bbox: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    startindex: Optional[int] = Query(None, ge=0, alias="startindex"),
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    exploration_status: Optional[str] = None,
) -> Dict[str, Any]:
    _require_ogc_enabled()
    if startindex is not None:
        offset = startindex

    bbox_t = _parse_bbox(bbox)
    q = db.query(MODSOccurrence)
    q = _apply_filters(q, commodity, region, occurrence_type, exploration_status, bbox_t)

    # Avoid COUNT() by using a lookahead row to decide next page link.
    rows = q.offset(offset).limit(limit + 1).all()
    has_next = len(rows) > limit
    rows = rows[:limit]

    features: List[Dict[str, Any]] = []
    for occ in rows:
        if occ.longitude is None or occ.latitude is None:
            continue
        features.append(_feature_from_occ(occ))

    base = _base_url(request)
    items_url = f"{base}/ogc/collections/mods_occurrences/items"

    links: List[Dict[str, Any]] = [
        {"rel": "self", "type": "application/geo+json", "href": str(request.url)},
        {"rel": "collection", "type": "application/json", "href": f"{base}/ogc/collections/mods_occurrences"},
    ]
    if offset > 0:
        prev_offset = max(0, offset - limit)
        links.append(
            {
                "rel": "prev",
                "type": "application/geo+json",
                "href": str(request.url.include_query_params(limit=limit, offset=prev_offset)),
            }
        )
    if has_next:
        links.append(
            {
                "rel": "next",
                "type": "application/geo+json",
                "href": str(request.url.include_query_params(limit=limit, offset=offset + limit)),
            }
        )

    audit_log(
        "ogc_items_query",
        {
            "bbox": bbox,
            "limit": limit,
            "offset": offset,
            "commodity": commodity,
            "region": region,
            "occurrence_type": occurrence_type,
            "exploration_status": exploration_status,
            "returned": len(features),
        },
    )

    return {
        "type": "FeatureCollection",
        "features": features,
        "numberReturned": len(features),
        "timeStamp": datetime.now(timezone.utc).isoformat(),
        "links": links,
    }


@router.get("/collections/mods_occurrences/items/{item_id}")
async def collection_item(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require_ogc_enabled()
    occ = db.query(MODSOccurrence).filter(MODSOccurrence.id == item_id).first()
    if occ is None:
        raise HTTPException(status_code=404, detail="Feature not found")
    if occ.longitude is None or occ.latitude is None:
        raise HTTPException(status_code=404, detail="Feature has no geometry")

    base = _base_url(request)
    audit_log("ogc_item_get", {"item_id": item_id})
    feat = _feature_from_occ(occ)
    feat["links"] = [
        {"rel": "self", "type": "application/geo+json", "href": str(request.url)},
        {"rel": "collection", "type": "application/json", "href": f"{base}/ogc/collections/mods_occurrences"},
    ]
    return feat

