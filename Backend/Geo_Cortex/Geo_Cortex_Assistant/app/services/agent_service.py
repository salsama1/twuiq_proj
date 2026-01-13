import json
from typing import Any, Dict, List, Optional, Tuple
import os

from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy import or_

from geoalchemy2.functions import ST_DWithin, ST_GeogFromText, ST_Distance

from app.models.dbmodels import MODSOccurrence
from app.models.schemas import OccurrenceInfo, NearestResult
from app.services.llm_service import generate_response
from app.services.router_service import handle_query, rag_retrieve
from app.services.chat_store import ChatMessage
from app.services.governance import audit_log, sanitize_text, feature_enabled

from shapely.geometry import shape as shapely_shape, mapping as shapely_mapping
from shapely.ops import unary_union


_AGENT_INSTRUCTIONS = """You are GeoCortex, an agentic RAG assistant for the MODS dataset.

You can either:
1) Answer directly, or
2) Call a tool to fetch/compute data before answering.

TOOL CALL FORMAT (respond with JSON ONLY):
{"action": "<tool_name>", "args": { ... }}

When you are ready to answer:
{"action": "final", "answer": "<your answer>"}

Available tools:
- search_mods: args {commodity?: str, region?: str, occurrence_type?: str, exploration_status?: str, limit?: int}
- nearby_mods: args {lat: float, lon: float, radius_km: float, limit?: int, commodity?: str}
- bbox_mods: args {min_lat: float, min_lon: float, max_lat: float, max_lon: float, limit?: int, commodity?: str}
- nearest_mods: args {lat: float, lon: float, limit?: int, commodity?: str}
- geojson_export: args {commodity?: str, region?: str, occurrence_type?: str, exploration_status?: str, lat?: float, lon?: float, radius_km?: float, limit?: int}
- csv_export: args {commodity?: str, region?: str, occurrence_type?: str, exploration_status?: str, lat?: float, lon?: float, radius_km?: float, limit?: int}
- stats_by_region: args {commodity?: str, occurrence_type?: str, limit?: int}
- importance_breakdown: args {commodity?: str, region?: str, occurrence_type?: str, exploration_status?: str}
- heatmap_bins: args {commodity?: str, region?: str, occurrence_type?: str, exploration_status?: str, bin_km?: float, limit?: int}
- commodity_stats: args {region?: str, occurrence_type?: str, limit?: int}
- qc_summary: args {}
- qc_duplicates_mods_id: args {limit?: int}
- qc_duplicates_coords: args {limit?: int}
- qc_outliers: args {limit?: int, expected_min_lon?: float, expected_min_lat?: float, expected_max_lon?: float, expected_max_lat?: float}
- ogc_items_link: args {bbox?: [minLon,minLat,maxLon,maxLat] | str, limit?: int, offset?: int, commodity?: str, region?: str, occurrence_type?: str, exploration_status?: str}
- publish_layer_instructions: args {ogc_items_url?: str}
- spatial_query: args {op: 'intersects'|'dwithin', geometry: object, distance_m?: float, commodity?: str, region?: str, occurrence_type?: str, exploration_status?: str, limit?: int, offset?: int}
- spatial_buffer: args {geometry: object, distance_m: float}
- spatial_nearest: args {geometry: object, limit?: int, commodity?: str, region?: str, occurrence_type?: str, exploration_status?: str}
- spatial_overlay: args {op: 'union'|'intersection'|'difference'|'symmetric_difference', a?: object, b?: object, feature_collection_ref?: 'uploaded', a_index?: int, b_index?: int}
- spatial_dissolve: args {feature_collection?: object, feature_collection_ref?: 'uploaded', by_property: str}
- spatial_join_mods_counts: args {feature_collection?: object, feature_collection_ref?: 'uploaded', predicate?: 'intersects'|'contains', id_property?: str}
- spatial_join_mods_nearest: args {feature_collection?: object, feature_collection_ref?: 'uploaded', id_property?: str}
- rasters_zonal_stats: args {raster_id: str, geometry?: object, geometry_ref?: 'uploaded', band?: int}
- For file-based workflows: you may pass geometry_ref="uploaded" instead of geometry, when using /agent/file.
- rag: args {query: str}

Rules:
- If the user asks for data (counts, lists, nearby, filters), call a tool first.
- Keep limits small by default (<= 25) unless user explicitly asks.
- If you call a tool, you must use its results in your final answer.

Notes:
- The field `occurrence_type` in MODS is typically values like: "Metallic", "Non Metallic", "Metallic and Non Metallic".
- Do NOT pass "Occurrence(s)" as occurrence_type. If user says "occurrences", ignore that field.
- If user says "mine(s)", filter using exploration_status containing "mine" (e.g. "Open pit mine", "Underground mine").
- If user says multiple regions (e.g. "Madinah and Makkah"), pass region as "Madinah Region, Makkah Region".
"""

_MUHANNED_PERSONA = """You are Muhanned.
You are a friendly, calm, highly competent geoscience assistant for the MODS dataset.
You speak naturally and conversationally. You ask 1 short clarifying question ONLY when necessary.
When you provide lists, keep them compact and structured.
Always ground answers in the provided RAG context and/or tool outputs. If context is insufficient, say so."""


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


def _split_multi(value: Optional[str]) -> List[str]:
    if not value:
        return []
    v = value.strip()
    if not v:
        return []
    v = v.replace(" and ", ",").replace(" AND ", ",")
    parts = [p.strip() for p in v.split(",")]
    return [p for p in parts if p]


def _clamp_int(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(v)
    except Exception:
        return default
    return max(lo, min(hi, n))


def _clamp_float(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        n = float(v)
    except Exception:
        return default
    return max(lo, min(hi, n))


def _normalize_region_value(value: Any) -> Optional[str]:
    """
    Accept region as:
    - "Makkah Region, Riyadh Region"
    - ["Makkah Region", "Riyadh Region"]
    """
    if value is None:
        return None
    if isinstance(value, list):
        parts = [str(x).strip() for x in value if str(x).strip()]
        return ", ".join(parts) if parts else None
    s = str(value).strip()
    return s or None


def _validate_lat_lon(lat: Any, lon: Any) -> Tuple[Optional[float], Optional[float]]:
    try:
        la = float(lat)
        lo = float(lon)
    except Exception:
        return None, None
    if not (-90.0 <= la <= 90.0 and -180.0 <= lo <= 180.0):
        return None, None
    return la, lo


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


def _tool_search_mods(
    db: Session,
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    exploration_status: Optional[str] = None,
    limit: int = 25,
) -> List[OccurrenceInfo]:
    q = db.query(MODSOccurrence)
    if commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    if region:
        regions = _split_multi(region)
        if regions:
            q = q.filter(or_(*[MODSOccurrence.admin_region.ilike(f"%{r}%") for r in regions]))
    if occurrence_type:
        q = q.filter(MODSOccurrence.occurrence_type.ilike(f"%{occurrence_type}%"))
    if exploration_status:
        q = q.filter(MODSOccurrence.exploration_status.ilike(f"%{exploration_status}%"))
    return [_to_occurrence_info(o) for o in q.limit(limit).all()]


def _tool_nearby_mods(
    db: Session,
    lat: float,
    lon: float,
    radius_km: float,
    limit: int = 25,
    commodity: Optional[str] = None,
) -> List[OccurrenceInfo]:
    q = db.query(MODSOccurrence)
    if commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    point = ST_GeogFromText(f"POINT({lon} {lat})")
    q = q.filter(ST_DWithin(MODSOccurrence.geom, point, radius_km * 1000.0))
    return [_to_occurrence_info(o) for o in q.limit(limit).all()]


def _tool_commodity_stats(
    db: Session,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    limit: int = 25,
) -> List[Dict[str, Any]]:
    q = db.query(MODSOccurrence.major_commodity, func.count(MODSOccurrence.id).label("count"))
    if region:
        q = q.filter(MODSOccurrence.admin_region.ilike(f"%{region}%"))
    if occurrence_type:
        q = q.filter(MODSOccurrence.occurrence_type.ilike(f"%{occurrence_type}%"))
    q = q.group_by(MODSOccurrence.major_commodity).order_by(func.count(MODSOccurrence.id).desc())
    return [{"major_commodity": mc, "count": int(c)} for mc, c in q.limit(limit).all()]


def _tool_bbox_mods(
    db: Session,
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    limit: int = 25,
    commodity: Optional[str] = None,
) -> List[OccurrenceInfo]:
    """
    Bounding-box filter using numeric lat/lon columns (fast & simple).
    """
    q = db.query(MODSOccurrence).filter(
        MODSOccurrence.latitude >= min_lat,
        MODSOccurrence.latitude <= max_lat,
        MODSOccurrence.longitude >= min_lon,
        MODSOccurrence.longitude <= max_lon,
    )
    if commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    return [_to_occurrence_info(o) for o in q.limit(limit).all()]


def _tool_nearest_mods(
    db: Session,
    lat: float,
    lon: float,
    limit: int = 25,
    commodity: Optional[str] = None,
) -> List[NearestResult]:
    """
    Nearest occurrences using PostGIS geography distance (meters).
    Returns dicts with distance_m + occurrence fields.
    """
    point = ST_GeogFromText(f"POINT({lon} {lat})")
    dist_m = ST_Distance(MODSOccurrence.geom, point).label("distance_m")
    q = db.query(MODSOccurrence, dist_m)
    if commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    rows = q.order_by(dist_m.asc()).limit(limit).all()
    out: List[NearestResult] = []
    for occ, d in rows:
        oi = _to_occurrence_info(occ)
        out.append(NearestResult(distance_m=float(d) if d is not None else None, occurrence=oi))
    return out


def _tool_geojson_export(
    db: Session,
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    exploration_status: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: Optional[float] = None,
    limit: int = 25,
) -> Dict[str, Any]:
    q = db.query(MODSOccurrence)
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
    if lat is not None and lon is not None and radius_km is not None:
        point = ST_GeogFromText(f"POINT({lon} {lat})")
        q = q.filter(ST_DWithin(MODSOccurrence.geom, point, radius_km * 1000.0))

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
    return {"type": "FeatureCollection", "features": features}

def _tool_csv_export(
    db: Session,
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    exploration_status: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: Optional[float] = None,
    limit: int = 5000,
) -> str:
    """
    Returns CSV text (for UI this is better as /export/csv, but agent can generate too).
    """
    import io
    import csv

    q = db.query(MODSOccurrence)
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
    if lat is not None and lon is not None and radius_km is not None:
        point = ST_GeogFromText(f"POINT({lon} {lat})")
        q = q.filter(ST_DWithin(MODSOccurrence.geom, point, radius_km * 1000.0))

    rows = q.limit(limit).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "mods_id", "english_name", "major_commodity", "admin_region", "latitude", "longitude"])
    for occ in rows:
        w.writerow([occ.id, occ.mods_id, occ.english_name, occ.major_commodity, occ.admin_region, occ.latitude, occ.longitude])
    return buf.getvalue()


def _tool_stats_by_region(
    db: Session,
    commodity: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    limit: int = 25,
) -> List[Dict[str, Any]]:
    q = db.query(MODSOccurrence.admin_region, func.count(MODSOccurrence.id).label("count"))
    if commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    occurrence_type = _normalize_occurrence_type(occurrence_type)
    if occurrence_type:
        q = q.filter(MODSOccurrence.occurrence_type.ilike(f"%{occurrence_type}%"))
    q = q.group_by(MODSOccurrence.admin_region).order_by(func.count(MODSOccurrence.id).desc()).limit(limit)
    return [{"admin_region": r, "count": int(c)} for r, c in q.all()]


def _tool_importance_breakdown(
    db: Session,
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    exploration_status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    q = db.query(MODSOccurrence.occurrence_importance, func.count(MODSOccurrence.id).label("count"))
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
    q = q.group_by(MODSOccurrence.occurrence_importance).order_by(func.count(MODSOccurrence.id).desc())
    return [{"occurrence_importance": imp, "count": int(c)} for imp, c in q.all()]


def _tool_heatmap_bins(
    db: Session,
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    exploration_status: Optional[str] = None,
    bin_km: float = 25.0,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    bin_deg = float(bin_km) / 111.32
    lon_bin = (func.floor(MODSOccurrence.longitude / bin_deg) * bin_deg).label("lon_bin")
    lat_bin = (func.floor(MODSOccurrence.latitude / bin_deg) * bin_deg).label("lat_bin")
    q = db.query(lon_bin, lat_bin, func.count(MODSOccurrence.id).label("count"))
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
    q = q.group_by(lon_bin, lat_bin).order_by(func.count(MODSOccurrence.id).desc()).limit(limit)
    return [{"lon": float(lon), "lat": float(lat), "count": int(c)} for lon, lat, c in q.all()]


def _tool_qc_summary(db: Session) -> Dict[str, Any]:
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
            (func.abs(MODSOccurrence.latitude) > 90.0) | (func.abs(MODSOccurrence.longitude) > 180.0),
        )
        .scalar()
        or 0
    )
    missing_geom = int(db.query(func.count(MODSOccurrence.id)).filter(MODSOccurrence.geom.is_(None)).scalar() or 0)
    dup_mods_groups = int(
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
    dup_coord_groups = int(
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
    return {
        "total_rows": total,
        "null_latitude_rows": null_lat,
        "null_longitude_rows": null_lon,
        "zero_coord_rows": zero_coords,
        "out_of_range_rows": out_of_range,
        "missing_geom_rows": missing_geom,
        "duplicate_mods_id_groups": dup_mods_groups,
        "duplicate_coord_groups": dup_coord_groups,
    }


def _tool_qc_duplicates_mods_id(db: Session, limit: int = 200) -> List[Dict[str, Any]]:
    rows = (
        db.query(MODSOccurrence.mods_id, func.count(MODSOccurrence.id).label("count"))
        .filter(MODSOccurrence.mods_id.isnot(None), MODSOccurrence.mods_id != "")
        .group_by(MODSOccurrence.mods_id)
        .having(func.count(MODSOccurrence.id) > 1)
        .order_by(func.count(MODSOccurrence.id).desc())
        .limit(limit)
        .all()
    )
    return [{"mods_id": m, "count": int(c)} for m, c in rows]


def _tool_qc_duplicates_coords(db: Session, limit: int = 200) -> List[Dict[str, Any]]:
    rows = (
        db.query(
            MODSOccurrence.latitude,
            MODSOccurrence.longitude,
            func.count(MODSOccurrence.id).label("count"),
        )
        .filter(MODSOccurrence.latitude.isnot(None), MODSOccurrence.longitude.isnot(None))
        .group_by(MODSOccurrence.latitude, MODSOccurrence.longitude)
        .having(func.count(MODSOccurrence.id) > 1)
        .order_by(func.count(MODSOccurrence.id).desc())
        .limit(limit)
        .all()
    )
    return [{"latitude": float(lat), "longitude": float(lon), "count": int(c)} for lat, lon, c in rows]


def _tool_qc_outliers(
    db: Session,
    limit: int = 200,
    expected_min_lon: Optional[float] = None,
    expected_min_lat: Optional[float] = None,
    expected_max_lon: Optional[float] = None,
    expected_max_lat: Optional[float] = None,
) -> Dict[str, Any]:
    invalid_q = db.query(MODSOccurrence).filter(
        (MODSOccurrence.latitude.is_(None))
        | (MODSOccurrence.longitude.is_(None))
        | ((MODSOccurrence.latitude == 0.0) & (MODSOccurrence.longitude == 0.0))
        | (func.abs(MODSOccurrence.latitude) > 90.0)
        | (func.abs(MODSOccurrence.longitude) > 180.0)
    )
    invalid_sub = invalid_q.with_entities(MODSOccurrence.id).subquery()
    invalid_count = int(db.query(func.count()).select_from(invalid_sub).scalar() or 0)

    expected_bbox_enabled = (
        expected_min_lon is not None
        and expected_min_lat is not None
        and expected_max_lon is not None
        and expected_max_lat is not None
    )
    expected_bbox_count: Optional[int] = None
    expected_q = None
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

    if expected_bbox_enabled and expected_q is not None and len(sample) < limit:
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

    return {
        "counts": {"invalid_coords": invalid_count, "outside_expected_bbox": expected_bbox_count},
        "expected_bbox": {
            "enabled": expected_bbox_enabled,
            "min_lon": expected_min_lon,
            "min_lat": expected_min_lat,
            "max_lon": expected_max_lon,
            "max_lat": expected_max_lat,
        },
        "sample": sample,
    }


def _tool_ogc_items_link(args: Dict[str, Any]) -> str:
    """
    Returns a ready-to-use URL for QGIS OGC API Features.
    """
    base = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    path = "/ogc/collections/mods_occurrences/items"

    bbox = args.get("bbox")
    if isinstance(bbox, list) and len(bbox) >= 4:
        bbox_str = ",".join(str(float(x)) for x in bbox[:4])
    elif isinstance(bbox, str) and bbox.strip():
        bbox_str = bbox.strip()
    else:
        bbox_str = None

    params: List[str] = []
    for k in ("commodity", "region", "occurrence_type", "exploration_status"):
        v = args.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            params.append(f"{k}={s}")

    limit = args.get("limit")
    offset = args.get("offset")
    if limit is not None:
        params.append(f"limit={int(limit)}")
    if offset is not None:
        params.append(f"offset={int(offset)}")
    if bbox_str:
        params.append(f"bbox={bbox_str}")

    qs = ("?" + "&".join(params)) if params else ""
    return f"{base}{path}{qs}"


def _tool_spatial_query(
    db: Session,
    op: str,
    geometry: Optional[Dict[str, Any]] = None,
    geometry_ref: Optional[str] = None,
    distance_m: Optional[float] = None,
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    exploration_status: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Agent tool version of /spatial/query.
    Returns a dict with total + featurecollection.
    """
    from sqlalchemy import or_, func, cast
    from geoalchemy2 import Geometry
    from geoalchemy2.functions import ST_GeomFromGeoJSON, ST_SetSRID, ST_Transform

    if geometry_ref == "uploaded" and geometry is None:
        from app.services.request_context import get_uploaded_geometry

        geometry = get_uploaded_geometry()
    if not isinstance(geometry, dict) or "type" not in geometry:
        raise ValueError("geometry must be a GeoJSON geometry object (or use geometry_ref='uploaded')")

    geom_4326 = ST_SetSRID(ST_GeomFromGeoJSON(json.dumps(geometry)), 4326)
    q = db.query(MODSOccurrence)

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

    pt_geom_4326 = cast(MODSOccurrence.geom, Geometry(geometry_type="POINT", srid=4326))
    if op == "intersects":
        q = q.filter(func.ST_Intersects(pt_geom_4326, geom_4326))
    elif op == "dwithin":
        if distance_m is None:
            raise ValueError("distance_m is required for dwithin")
        pt_3857 = ST_Transform(pt_geom_4326, 3857)
        geom_3857 = ST_Transform(geom_4326, 3857)
        q = q.filter(func.ST_DWithin(pt_3857, geom_3857, float(distance_m)))
    else:
        raise ValueError(f"Unsupported op: {op}")

    total = int(q.count())
    rows = q.offset(offset).limit(limit).all()
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
    return {"total": total, "geojson": fc}


def _tool_spatial_buffer(db: Session, geometry: Dict[str, Any], distance_m: float) -> Dict[str, Any]:
    """
    Returns a GeoJSON geometry of the buffered input (EPSG:4326).
    """
    from sqlalchemy import text as sql_text

    if geometry is None:
        from app.services.request_context import get_uploaded_geometry

        geometry = get_uploaded_geometry()
    if not isinstance(geometry, dict) or "type" not in geometry:
        raise ValueError("geometry must be a GeoJSON geometry object (or upload a file)")
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
        {"g": json.dumps(geometry), "d": float(distance_m)},
    ).first()
    if not r or not r[0]:
        raise ValueError("Failed to compute buffer geometry")
    return {"geometry": json.loads(r[0])}


def _tool_spatial_nearest(
    db: Session,
    geometry: Optional[Dict[str, Any]] = None,
    limit: int = 25,
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    exploration_status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    from sqlalchemy import or_, func, cast
    from geoalchemy2 import Geometry
    from geoalchemy2.functions import ST_Distance, ST_GeomFromGeoJSON, ST_SetSRID, ST_Transform

    if geometry is None:
        from app.services.request_context import get_uploaded_geometry

        geometry = get_uploaded_geometry()
    if not isinstance(geometry, dict) or "type" not in geometry:
        raise ValueError("geometry must be a GeoJSON geometry object (or upload a file)")

    geom_4326 = ST_SetSRID(ST_GeomFromGeoJSON(json.dumps(geometry)), 4326)
    geom_3857 = ST_Transform(geom_4326, 3857)

    q = db.query(MODSOccurrence)
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

    pt_geom_4326 = cast(MODSOccurrence.geom, Geometry(geometry_type="POINT", srid=4326))
    pt_3857 = ST_Transform(pt_geom_4326, 3857)
    dist_m = ST_Distance(pt_3857, geom_3857).label("distance_m")

    rows = q.with_entities(MODSOccurrence, dist_m).order_by(dist_m.asc()).limit(limit).all()
    out: List[Dict[str, Any]] = []
    for occ, d in rows:
        out.append({"distance_m": float(d) if d is not None else None, "occurrence": _to_occurrence_info(occ).model_dump()})
    return out


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """
    Best-effort extraction of a JSON object from model output.
    Some local models wrap JSON in prose; this finds the first {...} block.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None


def _extract_json_object_loose(text: str) -> Optional[Dict[str, Any]]:
    """
    More forgiving JSON extraction for planning: finds the first '{'..'}' and parses.
    """
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except Exception:
        return None


def _truncate_for_llm(value: Any, max_list: int = 25, max_str: int = 4000) -> Any:
    """
    Best-effort trimming so we can safely include tool outputs in LLM prompts.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value if len(value) <= max_str else value[:max_str] + "…"
    if isinstance(value, list):
        return [_truncate_for_llm(v, max_list=max_list, max_str=max_str) for v in value[:max_list]]
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in list(value.items())[:100]:
            out[str(k)] = _truncate_for_llm(v, max_list=max_list, max_str=max_str)
        return out
    return value


def _build_vega_charts(artifacts: Dict[str, Any]) -> List[Dict[str, Any]]:
    charts: List[Dict[str, Any]] = []

    # stats_by_region: [{admin_region, count}]
    sbr = artifacts.get("stats_by_region")
    if isinstance(sbr, list) and sbr:
        charts.append(
            {
                "name": "stats_by_region",
                "title": "Occurrences by admin region",
                "data": sbr,
                "vega_lite": {
                    "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                    "description": "Occurrences by admin region (bar chart).",
                    "data": {"name": "data"},
                    "mark": "bar",
                    "encoding": {
                        "x": {"field": "admin_region", "type": "nominal", "sort": "-y", "axis": {"labelAngle": -30}},
                        "y": {"field": "count", "type": "quantitative"},
                        "tooltip": [{"field": "admin_region"}, {"field": "count"}],
                    },
                },
            }
        )

    # commodity_stats: [{major_commodity, count}]
    cs = artifacts.get("commodity_stats")
    if isinstance(cs, list) and cs:
        charts.append(
            {
                "name": "commodity_stats",
                "title": "Top commodities (by count)",
                "data": cs,
                "vega_lite": {
                    "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                    "description": "Top commodities (bar chart).",
                    "data": {"name": "data"},
                    "mark": "bar",
                    "encoding": {
                        "x": {"field": "major_commodity", "type": "nominal", "sort": "-y", "axis": {"labelAngle": -30}},
                        "y": {"field": "count", "type": "quantitative"},
                        "tooltip": [{"field": "major_commodity"}, {"field": "count"}],
                    },
                },
            }
        )

    # importance_breakdown: [{occurrence_importance, count}]
    ib = artifacts.get("importance_breakdown")
    if isinstance(ib, list) and ib:
        charts.append(
            {
                "name": "importance_breakdown",
                "title": "Occurrence importance breakdown",
                "data": ib,
                "vega_lite": {
                    "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                    "description": "Importance breakdown (bar chart).",
                    "data": {"name": "data"},
                    "mark": "bar",
                    "encoding": {
                        "x": {"field": "occurrence_importance", "type": "nominal", "sort": "-y", "axis": {"labelAngle": -30}},
                        "y": {"field": "count", "type": "quantitative"},
                        "tooltip": [{"field": "occurrence_importance"}, {"field": "count"}],
                    },
                },
            }
        )

    # heatmap_bins: [{lon, lat, count}]
    hb = artifacts.get("heatmap_bins")
    if isinstance(hb, list) and hb:
        charts.append(
            {
                "name": "heatmap_bins",
                "title": "Spatial intensity (bin heatmap)",
                "data": hb,
                "vega_lite": {
                    "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                    "description": "Heatmap bins (circle size/color by count).",
                    "data": {"name": "data"},
                    "mark": {"type": "circle", "opacity": 0.7},
                    "encoding": {
                        "longitude": {"field": "lon", "type": "quantitative"},
                        "latitude": {"field": "lat", "type": "quantitative"},
                        "size": {"field": "count", "type": "quantitative"},
                        "color": {"field": "count", "type": "quantitative"},
                        "tooltip": [{"field": "lon"}, {"field": "lat"}, {"field": "count"}],
                    },
                },
            }
        )

    return charts


def run_workflow(
    db: Session,
    user_query: str,
    max_steps: int = 6,
    use_llm: bool = True,
    chat_history: Optional[List[ChatMessage]] = None,
) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]], Optional[List[OccurrenceInfo]], Dict[str, Any]]:
    """
    Workflow agent: produce an explicit plan, execute steps, then answer.
    Returns: (final_answer, plan_steps, tool_trace, last_occurrences, artifacts)
    """
    tool_trace: List[Dict[str, Any]] = []
    plan_steps: List[Dict[str, Any]] = []
    last_occurrences: Optional[List[OccurrenceInfo]] = None
    artifacts: Dict[str, Any] = {}

    # If there is an uploaded AOI geometry and user asks for common ops, plan deterministically.
    try:
        from app.services.request_context import get_uploaded_geometry

        uploaded = get_uploaded_geometry()
    except Exception:
        uploaded = None
    try:
        from app.services.request_context import get_uploaded_feature_collection

        uploaded_fc = get_uploaded_feature_collection()
    except Exception:
        uploaded_fc = None

    ql = user_query.lower()
    if uploaded is not None:
        if "buffer" in ql:
            plan_steps.append({"action": "spatial_buffer", "args": {"geometry": None, "distance_m": 50000.0}, "why": "User requested buffer of uploaded AOI."})
        if "nearest" in ql or "closest" in ql:
            plan_steps.append({"action": "spatial_nearest", "args": {"geometry": None, "limit": 25}, "why": "User requested nearest to uploaded AOI."})
        if "intersect" in ql or "clip" in ql:
            plan_steps.append({"action": "spatial_query", "args": {"op": "intersects", "geometry": None, "geometry_ref": "uploaded", "limit": 500}, "why": "User requested intersection with uploaded AOI."})

    if "qc" in ql or "quality" in ql or "duplicates" in ql:
        plan_steps.append({"action": "qc_summary", "args": {}, "why": "User asked for QC/quality."})

    # Add common “summary + charts” analytics deterministically when user asks.
    # This avoids relying on the planner when a query contains QC keywords.
    if "commodity" in ql or "commodities" in ql or "top commodities" in ql:
        plan_steps.append({"action": "commodity_stats", "args": {"limit": 15}, "why": "User asked for commodity breakdown/top commodities."})
    if "region" in ql or "regions" in ql or "by region" in ql:
        plan_steps.append({"action": "stats_by_region", "args": {"limit": 20}, "why": "User asked for counts by region."})
    if "importance" in ql:
        plan_steps.append({"action": "importance_breakdown", "args": {}, "why": "User asked for importance breakdown."})
    if "heatmap" in ql or "density" in ql or "hotspot" in ql:
        plan_steps.append({"action": "heatmap_bins", "args": {"bin_km": 50.0, "limit": 4000}, "why": "User asked for a spatial density/heatmap view."})

    # File-driven GIS toolbox ops (FeatureCollection based)
    if uploaded_fc is not None:
        if "dissolve" in ql:
            # best guess: common field names
            by_prop = "group" if "group" in ql else "name" if "name" in ql else "id"
            plan_steps.append({"action": "spatial_dissolve", "args": {"feature_collection_ref": "uploaded", "by_property": by_prop}, "why": "User requested dissolve on uploaded features."})
        if "spatial join" in ql or "join" in ql and ("count" in ql or "counts" in ql):
            plan_steps.append({"action": "spatial_join_mods_counts", "args": {"feature_collection_ref": "uploaded", "predicate": "intersects", "id_property": "id"}, "why": "User requested counts per polygon (spatial join)."})
        if "nearest join" in ql or ("join" in ql and "nearest" in ql):
            plan_steps.append({"action": "spatial_join_mods_nearest", "args": {"feature_collection_ref": "uploaded", "id_property": "id"}, "why": "User requested nearest join to MODS."})
        if ("overlay" in ql or "intersection" in ql or "union" in ql or "difference" in ql) and isinstance(uploaded_fc, dict):
            # If the uploaded FC contains >=2 geometries, overlay them.
            op = "intersection"
            if "union" in ql:
                op = "union"
            elif "difference" in ql:
                op = "difference"
            elif "symmetric" in ql:
                op = "symmetric_difference"
            plan_steps.append({"action": "spatial_overlay", "args": {"op": op, "feature_collection_ref": "uploaded", "a_index": 0, "b_index": 1}, "why": "User requested an overlay operation between uploaded geometries."})

    # If no deterministic plan, ask LLM to propose one.
    if not plan_steps and use_llm:
        rag_context, _ = rag_retrieve(user_query, k=6)
        history_block = ""
        if chat_history:
            lines = []
            for m in chat_history[-10:]:
                role = "User" if m.role == "user" else "Muhanned"
                lines.append(f"{role}: {m.content}")
            history_block = "\n".join(lines)

        planning_prompt = (
            _MUHANNED_PERSONA
            + "\n\nYou are a workflow planner. Produce ONLY JSON.\n"
            + "Return a JSON object: {\"plan\": [{\"action\": \"tool\", \"args\": {...}, \"why\": \"...\"}, ...]}\n"
            + f"Max steps: {max_steps}. Use only the available tools.\n"
            + "If the user refers to an uploaded file geometry, use geometry_ref=\"uploaded\" and omit geometry.\n"
            + "\nAvailable tools: search_mods, nearby_mods, bbox_mods, nearest_mods, geojson_export, csv_export, "
            + "stats_by_region, importance_breakdown, heatmap_bins, commodity_stats, "
            + "qc_summary, qc_duplicates_mods_id, qc_duplicates_coords, qc_outliers, "
            + "ogc_items_link, publish_layer_instructions, "
            + "spatial_query, spatial_buffer, spatial_nearest.\n"
            + "\nConversation so far:\n"
            + (history_block or "(none)")
            + "\n\nRAG context (optional):\n"
            + (rag_context or "(none)")
            + "\n\nUser query:\n"
            + user_query
        )
        model_out = generate_response(planning_prompt)
        obj = _extract_json_object_loose(model_out) or {}
        plan = obj.get("plan")
        if isinstance(plan, list):
            for step in plan[:max_steps]:
                if isinstance(step, dict) and isinstance(step.get("action"), str):
                    plan_steps.append(
                        {"action": step.get("action"), "args": step.get("args") or {}, "why": step.get("why")}
                    )

    # Execute the plan
    def _exec(action: str, args: Dict[str, Any]) -> None:
        nonlocal last_occurrences, artifacts

        # normalize + caps (reuse run_agent clamps for critical parts)
        if "region" in args:
            args["region"] = _normalize_region_value(args.get("region"))
        if "occurrence_type" in args:
            args["occurrence_type"] = _normalize_occurrence_type(args.get("occurrence_type"))

        if action in ("search_mods", "nearby_mods", "bbox_mods", "nearest_mods"):
            args["limit"] = _clamp_int(args.get("limit"), 1, 200, 25)
        if action in ("geojson_export",):
            args["limit"] = _clamp_int(args.get("limit"), 1, 2000, 200)
        if action in ("csv_export",):
            args["limit"] = _clamp_int(args.get("limit"), 1, 5000, 2000)
        if action in ("spatial_query",):
            args["limit"] = _clamp_int(args.get("limit"), 1, 5000, 500)
            args["offset"] = _clamp_int(args.get("offset"), 0, 500000, 0)
            if args.get("op") == "dwithin":
                args["distance_m"] = _clamp_float(args.get("distance_m"), 0.0, 2_000_000.0, 50_000.0)
        if action in ("spatial_buffer",):
            args["distance_m"] = _clamp_float(args.get("distance_m"), 0.0, 2_000_000.0, 50_000.0)
        if action in ("spatial_nearest",):
            args["limit"] = _clamp_int(args.get("limit"), 1, 500, 25)

        # governance gating for sensitive tools
        if action.startswith("qc_") and not feature_enabled("qc"):
            raise ValueError("QC is disabled by data governance policy.")
        if action.startswith("spatial_") and not feature_enabled("spatial"):
            raise ValueError("Spatial operations are disabled by data governance policy.")
        if action.startswith("rasters_") and not feature_enabled("rasters"):
            raise ValueError("Raster endpoints are disabled by data governance policy.")

        def _resolve_uploaded_fc() -> Optional[Dict[str, Any]]:
            try:
                from app.services.request_context import get_uploaded_feature_collection

                return get_uploaded_feature_collection()
            except Exception:
                return None

        def _resolve_uploaded_geom() -> Optional[Dict[str, Any]]:
            try:
                from app.services.request_context import get_uploaded_geometry

                return get_uploaded_geometry()
            except Exception:
                return None

        if action == "qc_summary":
            rep = _tool_qc_summary(db)
            artifacts["qc_summary"] = rep
            tool_trace.append({"tool": action, "args": {}, "keys": list(rep.keys())})
        elif action == "qc_duplicates_mods_id":
            rows = _tool_qc_duplicates_mods_id(db, **args)
            artifacts["qc_duplicates_mods_id"] = rows
            tool_trace.append({"tool": action, "args": args, "groups": len(rows)})
        elif action == "qc_duplicates_coords":
            rows = _tool_qc_duplicates_coords(db, **args)
            artifacts["qc_duplicates_coords"] = rows
            tool_trace.append({"tool": action, "args": args, "groups": len(rows)})
        elif action == "qc_outliers":
            rep = _tool_qc_outliers(db, **args)
            artifacts["qc_outliers"] = rep
            tool_trace.append({"tool": action, "args": args, "returned": len((rep or {}).get("sample") or [])})
        elif action == "spatial_query":
            rep = _tool_spatial_query(db, **args)
            artifacts["spatial_total"] = int(rep.get("total") or 0)
            artifacts["spatial_geojson"] = rep.get("geojson")
            tool_trace.append({"tool": action, "args": args, "features_count": len((rep.get("geojson") or {}).get("features", []))})
        elif action == "spatial_buffer":
            rep = _tool_spatial_buffer(db, **args)
            artifacts["spatial_buffer_geometry"] = rep.get("geometry")
            tool_trace.append({"tool": action, "args": args})
        elif action == "spatial_nearest":
            rows = _tool_spatial_nearest(db, **args)
            artifacts["spatial_nearest"] = rows
            tool_trace.append({"tool": action, "args": args, "results_count": len(rows)})
        elif action == "spatial_overlay":
            fc = None
            if args.get("feature_collection_ref") == "uploaded":
                fc = _resolve_uploaded_fc()
            a = args.get("a")
            b = args.get("b")
            if (a is None or b is None) and isinstance(fc, dict):
                feats = fc.get("features") if isinstance(fc.get("features"), list) else []
                ai = _clamp_int(args.get("a_index"), 0, 999999, 0)
                bi = _clamp_int(args.get("b_index"), 0, 999999, 1)
                try:
                    a = (feats[ai] or {}).get("geometry")
                    b = (feats[bi] or {}).get("geometry")
                except Exception:
                    a = None
                    b = None
            if not isinstance(a, dict) or not isinstance(b, dict):
                raise ValueError("spatial_overlay requires geometries a and b (or an uploaded FeatureCollection with >=2 features).")
            op = str(args.get("op") or "intersection")
            ga = shapely_shape(a)
            gb = shapely_shape(b)
            if op == "union":
                out = ga.union(gb)
            elif op == "intersection":
                out = ga.intersection(gb)
            elif op == "difference":
                out = ga.difference(gb)
            elif op == "symmetric_difference":
                out = ga.symmetric_difference(gb)
            else:
                raise ValueError(f"Unsupported overlay op: {op}")
            artifacts["overlay_geometry"] = shapely_mapping(out)
            tool_trace.append({"tool": action, "args": args})
        elif action == "spatial_dissolve":
            fc = args.get("feature_collection")
            if args.get("feature_collection_ref") == "uploaded":
                fc = _resolve_uploaded_fc()
            if not isinstance(fc, dict) or fc.get("type") != "FeatureCollection":
                raise ValueError("spatial_dissolve requires a GeoJSON FeatureCollection.")
            by_prop = str(args.get("by_property") or "").strip()
            if not by_prop:
                raise ValueError("spatial_dissolve requires by_property.")
            feats = fc.get("features") if isinstance(fc.get("features"), list) else []
            groups: Dict[str, List[Any]] = {}
            for f in feats[:50000]:
                if not isinstance(f, dict) or f.get("type") != "Feature":
                    continue
                geom = f.get("geometry")
                props = f.get("properties") if isinstance(f.get("properties"), dict) else {}
                if not isinstance(geom, dict) or "type" not in geom:
                    continue
                key = props.get(by_prop)
                k = str(key if key is not None else "(null)")
                try:
                    groups.setdefault(k, []).append(shapely_shape(geom))
                except Exception:
                    continue
            out_features: List[Dict[str, Any]] = []
            for k, shapes in groups.items():
                if not shapes:
                    continue
                merged = unary_union(shapes)
                out_features.append({"type": "Feature", "geometry": shapely_mapping(merged), "properties": {by_prop: k, "feature_count": len(shapes)}})
            artifacts["dissolved_feature_collection"] = {"type": "FeatureCollection", "features": out_features}
            tool_trace.append({"tool": action, "args": {"by_property": by_prop}, "features_count": len(out_features)})
        elif action == "spatial_join_mods_counts":
            fc = args.get("feature_collection")
            if args.get("feature_collection_ref") == "uploaded":
                fc = _resolve_uploaded_fc()
            if not isinstance(fc, dict) or fc.get("type") != "FeatureCollection":
                raise ValueError("spatial_join_mods_counts requires a GeoJSON FeatureCollection.")
            predicate = str(args.get("predicate") or "intersects")
            id_prop = str(args.get("id_property") or "id")
            feats = fc.get("features") if isinstance(fc.get("features"), list) else []
            out_feats: List[Dict[str, Any]] = []
            pt_geom_4326 = cast(MODSOccurrence.geom, Geometry(geometry_type="POINT", srid=4326))
            for f in feats[:5000]:
                if not isinstance(f, dict) or f.get("type") != "Feature":
                    continue
                geom = f.get("geometry")
                if not isinstance(geom, dict) or "type" not in geom:
                    continue
                props = f.get("properties") if isinstance(f.get("properties"), dict) else {}
                poly_4326 = ST_SetSRID(ST_GeomFromGeoJSON(json.dumps(geom)), 4326)
                q = db.query(func.count(MODSOccurrence.id))
                if predicate == "contains":
                    q = q.filter(func.ST_Contains(poly_4326, pt_geom_4326))
                else:
                    q = q.filter(func.ST_Intersects(pt_geom_4326, poly_4326))
                count_val = int(q.scalar() or 0)
                props_out = dict(props)
                props_out["mods_count"] = count_val
                props_out.setdefault(id_prop, props.get(id_prop))
                out_feats.append({"type": "Feature", "geometry": geom, "properties": props_out})
            artifacts["join_counts_feature_collection"] = {"type": "FeatureCollection", "features": out_feats}
            tool_trace.append({"tool": action, "args": {"predicate": predicate}, "features_count": len(out_feats)})
        elif action == "spatial_join_mods_nearest":
            fc = args.get("feature_collection")
            if args.get("feature_collection_ref") == "uploaded":
                fc = _resolve_uploaded_fc()
            if not isinstance(fc, dict) or fc.get("type") != "FeatureCollection":
                raise ValueError("spatial_join_mods_nearest requires a GeoJSON FeatureCollection.")
            id_prop = str(args.get("id_property") or "id")
            feats = fc.get("features") if isinstance(fc.get("features"), list) else []
            pt_geom_4326 = cast(MODSOccurrence.geom, Geometry(geometry_type="POINT", srid=4326))
            pt_3857 = ST_Transform(pt_geom_4326, 3857)
            out_rows: List[Dict[str, Any]] = []
            for f in feats[:5000]:
                if not isinstance(f, dict) or f.get("type") != "Feature":
                    continue
                geom = f.get("geometry")
                if not isinstance(geom, dict) or "type" not in geom:
                    continue
                props = f.get("properties") if isinstance(f.get("properties"), dict) else {}
                fid = props.get(id_prop)
                geom_4326 = ST_SetSRID(ST_GeomFromGeoJSON(json.dumps(geom)), 4326)
                geom_3857 = ST_Transform(geom_4326, 3857)
                dist_m = ST_Distance(pt_3857, geom_3857).label("distance_m")
                row = db.query(MODSOccurrence, dist_m).order_by(dist_m.asc()).limit(1).first()
                if not row:
                    out_rows.append({"feature_id": fid, "distance_m": None, "nearest": None})
                    continue
                occ, d = row
                out_rows.append({"feature_id": fid, "distance_m": float(d) if d is not None else None, "nearest": _to_occurrence_info(occ).model_dump()})
            artifacts["join_nearest_results"] = out_rows
            tool_trace.append({"tool": action, "args": {"id_property": id_prop}, "results_count": len(out_rows)})
        elif action == "rasters_zonal_stats":
            raster_id = str(args.get("raster_id") or "").strip()
            if not raster_id:
                raise ValueError("rasters_zonal_stats requires raster_id")
            geom = args.get("geometry")
            if args.get("geometry_ref") == "uploaded":
                geom = _resolve_uploaded_geom()
            if not isinstance(geom, dict) or "type" not in geom:
                raise ValueError("rasters_zonal_stats requires a GeoJSON geometry (or geometry_ref='uploaded').")
            band = _clamp_int(args.get("band"), 1, 1000, 1)
            # Call same logic as rasters router (inline, to avoid HTTP hop)
            from app.services.raster_service import RASTERS_DIR
            import numpy as np
            import rasterio
            from rasterio.mask import mask
            from rasterio.warp import transform_geom

            d = RASTERS_DIR / raster_id
            files = [p for p in d.iterdir() if p.is_file()] if d.exists() else []
            if not files:
                raise ValueError("Raster not found")
            path = files[0]
            with rasterio.open(path) as ds:
                g2 = geom
                if ds.crs and str(ds.crs).upper() not in ("EPSG:4326", "WGS84"):
                    g2 = transform_geom("EPSG:4326", ds.crs, g2, precision=6)
                out, _ = mask(ds, [g2], crop=True, filled=False)
                if band < 1 or band > ds.count:
                    raise ValueError(f"Invalid band={band}. Raster has {ds.count} band(s).")
                arr = out[band - 1]
                data = np.asarray(arr)
                mask_arr = np.ma.getmaskarray(arr)
                valid = data[~mask_arr]
                if valid.size == 0:
                    stats: Dict[str, Any] = {"count": 0, "min": None, "max": None, "mean": None, "std": None}
                else:
                    stats = {"count": int(valid.size), "min": float(np.min(valid)), "max": float(np.max(valid)), "mean": float(np.mean(valid)), "std": float(np.std(valid))}
            artifacts.setdefault("zonal_stats", [])
            artifacts["zonal_stats"].append({"raster_id": raster_id, "band": band, "stats": stats})
            tool_trace.append({"tool": action, "args": {"raster_id": raster_id, "band": band}, "raw": {"stats": stats}})
        elif action == "ogc_items_link":
            url = _tool_ogc_items_link(args)
            artifacts["ogc_items_url"] = url
            tool_trace.append({"tool": action, "args": args, "url": url})
        elif action == "publish_layer_instructions":
            url = str(args.get("ogc_items_url") or artifacts.get("ogc_items_url") or "").strip() or _tool_ogc_items_link({})
            instructions = (
                "QGIS (OGC API Features) quick add:\n"
                "1) Open QGIS → Data Source Manager\n"
                "2) Find 'OGC API - Features'\n"
                f"3) New connection → URL: {url}\n"
                "4) Connect → choose 'mods_occurrences' → Add\n"
            )
            artifacts["qgis_instructions"] = instructions
            tool_trace.append({"tool": action, "args": {"ogc_items_url": url}, "chars": len(instructions)})
        elif action == "geojson_export":
            geojson = _tool_geojson_export(db, **args)
            artifacts["geojson"] = geojson
            tool_trace.append({"tool": action, "args": args, "features_count": len(geojson.get("features", []))})
        elif action == "csv_export":
            csv_text = _tool_csv_export(db, **args)
            artifacts["csv"] = csv_text
            tool_trace.append({"tool": action, "args": args, "csv_bytes": len(csv_text.encode("utf-8"))})
        elif action == "search_mods":
            results = _tool_search_mods(db, **args)
            last_occurrences = results
            tool_trace.append({"tool": action, "args": args, "results_count": len(results)})
        elif action == "nearby_mods":
            results = _tool_nearby_mods(db, **args)
            last_occurrences = results
            tool_trace.append({"tool": action, "args": args, "results_count": len(results)})
        elif action == "bbox_mods":
            results = _tool_bbox_mods(db, **args)
            last_occurrences = results
            tool_trace.append({"tool": action, "args": args, "results_count": len(results)})
        elif action == "nearest_mods":
            results = _tool_nearest_mods(db, **args)
            artifacts["nearest_results"] = results
            tool_trace.append({"tool": action, "args": args, "results_count": len(results)})
        elif action == "stats_by_region":
            rows = _tool_stats_by_region(db, **args)
            artifacts["stats_by_region"] = rows
            tool_trace.append({"tool": action, "args": args, "rows": len(rows)})
        elif action == "importance_breakdown":
            rows = _tool_importance_breakdown(db, **args)
            artifacts["importance_breakdown"] = rows
            tool_trace.append({"tool": action, "args": args, "rows": len(rows)})
        elif action == "heatmap_bins":
            rows = _tool_heatmap_bins(db, **args)
            artifacts["heatmap_bins"] = rows
            tool_trace.append({"tool": action, "args": args, "bins": len(rows)})
        elif action == "commodity_stats":
            rows = _tool_commodity_stats(db, **args)
            artifacts["commodity_stats"] = rows
            tool_trace.append({"tool": action, "args": args, "rows": len(rows)})
        else:
            tool_trace.append({"tool": "unknown_step", "raw": {"action": action, "args": args}})

    audit_log("workflow_plan", {"query": user_query, "steps": len(plan_steps)})
    for step in plan_steps[:max_steps]:
        action = str(step.get("action") or "")
        args = step.get("args") or {}
        if not action:
            continue
        try:
            _exec(action, dict(args))
            audit_log("workflow_step", {"action": action})
        except Exception as e:
            tool_trace.append({"tool": action, "args": args, "error": str(e)})
            audit_log("workflow_step_error", {"action": action, "error": str(e)})

    # Produce final answer (conversational) grounded in tool results
    rag_context, rag_occs = rag_retrieve(user_query, k=6)
    if rag_occs and not last_occurrences:
        last_occurrences = rag_occs

    # Always attach chart-ready outputs if possible
    charts = _build_vega_charts(artifacts)
    if charts:
        artifacts["charts"] = charts

    if not use_llm:
        # Deterministic fallback for offline/fast mode
        bits: List[str] = []
        if artifacts.get("qc_summary"):
            bits.append(f"QC summary: {json.dumps(artifacts['qc_summary'], ensure_ascii=False)}")
        if artifacts.get("ogc_items_url"):
            bits.append(f"OGC items URL: {artifacts['ogc_items_url']}")
        if artifacts.get("qgis_instructions"):
            bits.append(str(artifacts["qgis_instructions"]))
        if artifacts.get("spatial_total") is not None:
            bits.append(f"Spatial results total: {artifacts.get('spatial_total')}")
        if artifacts.get("spatial_nearest"):
            bits.append(f"Spatial nearest returned: {len(artifacts.get('spatial_nearest') or [])}")
        if artifacts.get("geojson"):
            bits.append(f"GeoJSON export features: {len((artifacts.get('geojson') or {}).get('features', []))}")
        if artifacts.get("csv"):
            bits.append(f"CSV export bytes: {len(str(artifacts.get('csv')).encode('utf-8'))}")
        answer = "\n".join(bits) if bits else "Workflow executed (offline mode). No summary artifacts were produced."
    else:
        artifacts_preview = {
            "qc_summary": _truncate_for_llm(artifacts.get("qc_summary")),
            "qc_outliers": _truncate_for_llm(artifacts.get("qc_outliers")),
            "stats_by_region": _truncate_for_llm(artifacts.get("stats_by_region")),
            "commodity_stats": _truncate_for_llm(artifacts.get("commodity_stats")),
            "importance_breakdown": _truncate_for_llm(artifacts.get("importance_breakdown")),
            "spatial_total": artifacts.get("spatial_total"),
            "ogc_items_url": artifacts.get("ogc_items_url"),
            "charts": _truncate_for_llm(artifacts.get("charts"), max_list=6),
        }
        scratch = json.dumps({"plan": plan_steps, "tool_outputs": artifacts_preview}, ensure_ascii=False)
        final_prompt = (
            _MUHANNED_PERSONA
            + "\n\nUser query:\n"
            + user_query
            + "\n\nRAG context (from MODS):\n"
            + (rag_context or "(none)")
            + "\n\nWorkflow plan + tool outputs summary:\n"
            + scratch
            + "\n\nWrite a helpful answer for a geospatial specialist. "
            + "Summarize the key findings from tool_outputs (counts, top regions/commodities, QC flags). "
            + "If charts are available, say what each chart shows. "
            + "Mention any QGIS-ready links in tool_outputs (ogc_items_url) and where to find outputs."
        )
        answer = generate_response(final_prompt)
        # If the LLM timed out or errored, fall back to a deterministic summary
        # so the user still gets a useful “human-facing” response.
        if isinstance(answer, str) and (answer.startswith("LLM call timed out") or answer.startswith("LLM error")):
            bits: List[str] = [
                "LLM summary was unavailable, so here is an automatic summary of the computed results:"
            ]
            if artifacts.get("qc_summary"):
                bits.append(f"- QC summary: {json.dumps(artifacts['qc_summary'], ensure_ascii=False)}")
            if artifacts.get("commodity_stats"):
                bits.append(f"- Top commodities rows: {len(artifacts.get('commodity_stats') or [])}")
            if artifacts.get("stats_by_region"):
                bits.append(f"- Regions rows: {len(artifacts.get('stats_by_region') or [])}")
            if artifacts.get("importance_breakdown"):
                bits.append(f"- Importance rows: {len(artifacts.get('importance_breakdown') or [])}")
            if artifacts.get("heatmap_bins"):
                bits.append(f"- Heatmap bins: {len(artifacts.get('heatmap_bins') or [])}")
            if artifacts.get("charts"):
                bits.append(f"- Charts generated: {len(artifacts.get('charts') or [])} (see artifacts.charts)")
            if artifacts.get("ogc_items_url"):
                bits.append(f"- OGC items URL: {artifacts.get('ogc_items_url')}")
            answer = "\n".join(bits)
    audit_log("workflow_final", {"query": user_query})
    return sanitize_text(answer), plan_steps, tool_trace, last_occurrences, artifacts
    try:
        return json.loads(text[start : end + 1])
    except Exception:
        return None


def run_agent(
    db: Session,
    user_query: str,
    max_steps: int = 3,
    chat_history: Optional[List[ChatMessage]] = None,
) -> Tuple[str, List[Dict[str, Any]], Optional[List[OccurrenceInfo]], Dict[str, Any]]:
    """
    Simple JSON-tool-loop agent.
    Returns (final_answer, tool_trace, occurrences_if_any).
    """
    tool_trace: List[Dict[str, Any]] = []
    last_occurrences: Optional[List[OccurrenceInfo]] = None
    artifacts: Dict[str, Any] = {}
    seen_calls: set[str] = set()
    debug_trace = os.getenv("AGENT_DEBUG_TRACE", "0").lower() in ("1", "true", "yes")

    def _infer_regions_from_query() -> List[str]:
        # Use actual DB region names; match if the base token appears in the query.
        try:
            rows = db.query(MODSOccurrence.admin_region).distinct().all()
            regions = [r[0] for r in rows if r and r[0]]
        except Exception:
            regions = []
        q = user_query.lower()
        out: List[str] = []
        for reg in regions:
            base = reg.lower()
            base = base.replace(" region", "").replace(" province", "").strip()
            # allow common spelling: madinah/medina
            if base == "madinah":
                tokens = {"madinah", "medina"}
            else:
                tokens = {base}
            if any(t in q for t in tokens):
                out.append(reg)
        # de-dupe, keep order
        seen = set()
        final = []
        for r in out:
            if r in seen:
                continue
            seen.add(r)
            final.append(r)
        return final

    def _infer_commodity_from_query() -> Optional[str]:
        q = user_query.lower()
        # small high-signal set; can expand later
        if "gold" in q:
            return "Gold"
        if "copper" in q:
            return "Copper"
        if "zinc" in q:
            return "Zinc"
        if "silver" in q:
            return "Silver"
        return None

    # Pragmatic: "show/map ... mines in <regions>" should ALWAYS visualize correctly.
    # This avoids local model tool-use glitches and makes the UI feel reliable.
    ql = user_query.lower()
    if ("show" in ql or "map" in ql) and ("mine" in ql):
        regions = _infer_regions_from_query()
        commodity = _infer_commodity_from_query()
        if regions and commodity:
            region_guess = ", ".join(regions)
            geojson = _tool_geojson_export(
                db,
                commodity=commodity,
                region=region_guess,
                exploration_status="mine",
                limit=400,
            )
            artifacts["geojson"] = geojson
            tool_trace.append(
                {
                    "tool": "auto_geojson_export",
                    "args": {"commodity": commodity, "region": region_guess, "exploration_status": "mine", "limit": 400},
                    "features_count": len(geojson.get("features", [])),
                }
            )
            answer = (
                f"I mapped {commodity} mine locations in {region_guess} "
                f"(filtered by exploration_status containing 'mine'). "
                f"Showing {len(geojson.get('features', []))} points on the map."
            )
            audit_log(
                "agent_auto_visualize_mines",
                {
                    "query": user_query,
                    "commodity": commodity,
                    "region": region_guess,
                    "features": len(geojson.get("features", [])),
                },
            )
            return sanitize_text(answer), tool_trace, last_occurrences, artifacts

    # Pragmatic file-geometry fast paths (avoid LLM dependency for common GIS ops)
    # If the request-scoped uploaded geometry is present, we can run certain ops deterministically.
    try:
        from app.services.request_context import get_uploaded_geometry

        up = get_uploaded_geometry()
    except Exception:
        up = None
    if up is not None:
        ql2 = user_query.lower()
        if "nearest" in ql2 or "closest" in ql2:
            rows = _tool_spatial_nearest(db, geometry=None, limit=25)
            artifacts["spatial_nearest"] = rows
            audit_log("agent_file_fast_spatial_nearest", {"query": user_query, "rows": len(rows)})
            return (
                f"Computed {len(rows)} nearest results. See `artifacts.spatial_nearest`.",
                tool_trace,
                last_occurrences,
                artifacts,
            )
        if "buffer" in ql2:
            geom = _tool_spatial_buffer(db, geometry=None, distance_m=50000.0).get("geometry")
            artifacts["spatial_buffer_geometry"] = geom
            audit_log("agent_file_fast_spatial_buffer", {"query": user_query})
            return (
                "Generated buffer geometry. See `artifacts.spatial_buffer_geometry`.",
                tool_trace,
                last_occurrences,
                artifacts,
            )

    # Always do RAG retrieval up-front so the agent is grounded in MODS.
    rag_context, rag_occs = rag_retrieve(user_query, k=6)
    if rag_occs:
        last_occurrences = rag_occs
    scratchpad = ""
    scratchpad += f"\n- RAG retrieved {len(rag_occs)} occurrences; context chars: {len(rag_context)}\n"

    history_block = ""
    if chat_history:
        lines = []
        for m in chat_history[-12:]:
            role = "User" if m.role == "user" else "Muhanned"
            lines.append(f"{role}: {m.content}")
        history_block = "\n".join(lines)

    for _ in range(max_steps):
        prompt = (
            _MUHANNED_PERSONA
            + "\n\n"
            + _AGENT_INSTRUCTIONS
            + "\n\nConversation so far:\n"
            + (history_block or "(none)")
            + "\n\nRAG context (from MODS):\n"
            + (rag_context or "(none)")
            + "\n\nUser query:\n"
            + user_query
            + "\n\nTool results so far:\n"
            + (scratchpad or "(none)")
        )
        model_out = generate_response(prompt)
        action_obj = _extract_json_object(model_out)

        # If the model didn't follow the tool JSON format:
        # - If we already ran tools, force a final answer using gathered results.
        # - Otherwise, treat the raw model output as the answer.
        if not action_obj or "action" not in action_obj:
            if tool_trace:
                break
            audit_log("agent_raw_answer", {"query": user_query})
            return sanitize_text(model_out), tool_trace, last_occurrences, artifacts

        action = action_obj.get("action")
        if action == "final":
            return str(action_obj.get("answer", "")), tool_trace, last_occurrences, artifacts

        args = action_obj.get("args") or {}
        # --- Guard rails: normalize + hard-cap tool arguments ---
        # Normalize region values (string/list)
        if "region" in args:
            args["region"] = _normalize_region_value(args.get("region"))

        # Normalize occurrence_type placeholders
        if "occurrence_type" in args:
            args["occurrence_type"] = _normalize_occurrence_type(args.get("occurrence_type"))

        # Normalize exploration_status empty strings
        if "exploration_status" in args:
            v = args.get("exploration_status")
            if v is not None:
                vv = str(v).strip()
                args["exploration_status"] = vv or None

        # Clamp limits per tool
        if action in ("search_mods", "nearby_mods", "bbox_mods", "nearest_mods"):
            args["limit"] = _clamp_int(args.get("limit"), 1, 200, 25)
        if action in ("geojson_export",):
            args["limit"] = _clamp_int(args.get("limit"), 1, 2000, 200)
        if action in ("csv_export",):
            args["limit"] = _clamp_int(args.get("limit"), 1, 5000, 2000)
        if action in ("stats_by_region", "commodity_stats"):
            args["limit"] = _clamp_int(args.get("limit"), 1, 200, 25)
        if action in ("heatmap_bins",):
            args["limit"] = _clamp_int(args.get("limit"), 1, 500, 200)
            args["bin_km"] = _clamp_float(args.get("bin_km", 25.0), 1.0, 250.0, 25.0)
        if action in ("qc_duplicates_mods_id", "qc_duplicates_coords", "qc_outliers"):
            args["limit"] = _clamp_int(args.get("limit"), 1, 5000, 200)
        if action in ("spatial_query",):
            args["limit"] = _clamp_int(args.get("limit"), 1, 5000, 500)
            args["offset"] = _clamp_int(args.get("offset"), 0, 500000, 0)
            if args.get("op") == "dwithin":
                args["distance_m"] = _clamp_float(args.get("distance_m"), 0.0, 2_000_000.0, 50_000.0)
        if action in ("spatial_buffer",):
            args["distance_m"] = _clamp_float(args.get("distance_m"), 0.0, 2_000_000.0, 50_000.0)
        if action in ("spatial_nearest",):
            args["limit"] = _clamp_int(args.get("limit"), 1, 500, 25)

        # Clamp geo inputs
        if action in ("nearby_mods",):
            la, lo = _validate_lat_lon(args.get("lat"), args.get("lon"))
            if la is None or lo is None:
                raise ValueError("Invalid lat/lon")
            args["lat"], args["lon"] = la, lo
            args["radius_km"] = _clamp_float(args.get("radius_km"), 0.1, 1000.0, 50.0)

        if action in ("nearest_mods",):
            la, lo = _validate_lat_lon(args.get("lat"), args.get("lon"))
            if la is None or lo is None:
                raise ValueError("Invalid lat/lon")
            args["lat"], args["lon"] = la, lo

        if action in ("bbox_mods",):
            args["min_lat"] = _clamp_float(args.get("min_lat"), -90.0, 90.0, -90.0)
            args["max_lat"] = _clamp_float(args.get("max_lat"), -90.0, 90.0, 90.0)
            args["min_lon"] = _clamp_float(args.get("min_lon"), -180.0, 180.0, -180.0)
            args["max_lon"] = _clamp_float(args.get("max_lon"), -180.0, 180.0, 180.0)

        # If we've already produced the artifact for this tool, stop (prevents multi-tool spam).
        already = (
            (action == "heatmap_bins" and "heatmap_bins" in artifacts)
            or (action == "stats_by_region" and "stats_by_region" in artifacts)
            or (action == "importance_breakdown" and "importance_breakdown" in artifacts)
            or (action == "geojson_export" and "geojson" in artifacts)
            or (action == "csv_export" and "csv" in artifacts)
            or (action == "nearest_mods" and "nearest_results" in artifacts)
            or (action == "qc_summary" and "qc_summary" in artifacts)
            or (action == "qc_duplicates_mods_id" and "qc_duplicates_mods_id" in artifacts)
            or (action == "qc_duplicates_coords" and "qc_duplicates_coords" in artifacts)
            or (action == "qc_outliers" and "qc_outliers" in artifacts)
            or (action == "ogc_items_link" and "ogc_items_url" in artifacts)
            or (action == "publish_layer_instructions" and "qgis_instructions" in artifacts)
            or (action == "spatial_query" and "spatial_geojson" in artifacts)
            or (action == "spatial_buffer" and "spatial_buffer_geometry" in artifacts)
            or (action == "spatial_nearest" and "spatial_nearest" in artifacts)
        )
        if already:
            if debug_trace:
                tool_trace.append({"tool": "redundant_tool_call", "raw": action_obj})
            break

        call_key = f"{action}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
        if call_key in seen_calls:
            # Model is looping on the same tool call; stop and force a final answer.
            if debug_trace:
                tool_trace.append({"tool": "loop_detected", "raw": action_obj})
            break
        seen_calls.add(call_key)

        try:
            if action == "search_mods":
                results = _tool_search_mods(db, **args)
                last_occurrences = results
                tool_trace.append({"tool": action, "args": args, "results_count": len(results)})
                scratchpad += f"\n- search_mods returned {len(results)} rows\n"
            elif action == "nearby_mods":
                results = _tool_nearby_mods(db, **args)
                last_occurrences = results
                tool_trace.append({"tool": action, "args": args, "results_count": len(results)})
                scratchpad += f"\n- nearby_mods returned {len(results)} rows\n"
            elif action == "commodity_stats":
                stats = _tool_commodity_stats(db, **args)
                tool_trace.append({"tool": action, "args": args, "results_preview": stats[:5]})
                scratchpad += f"\n- commodity_stats top5: {stats[:5]}\n"
            elif action == "bbox_mods":
                results = _tool_bbox_mods(db, **args)
                last_occurrences = results
                tool_trace.append({"tool": action, "args": args, "results_count": len(results)})
                scratchpad += f"\n- bbox_mods returned {len(results)} rows\n"
            elif action == "nearest_mods":
                results = _tool_nearest_mods(db, **args)
                tool_trace.append({"tool": action, "args": args, "results_count": len(results)})
                artifacts["nearest_results"] = results
                # Provide a small preview so the model can summarize.
                preview = [r.model_dump() for r in results[:5]]
                scratchpad += f"\n- nearest_mods returned {len(results)} rows; preview: {preview}\n"
            elif action == "geojson_export":
                geojson = _tool_geojson_export(db, **args)
                artifacts["geojson"] = geojson
                tool_trace.append({"tool": action, "args": args, "features_count": len(geojson.get('features', []))})
                scratchpad += f"\n- geojson_export produced {len(geojson.get('features', []))} features\n"
            elif action == "csv_export":
                csv_text = _tool_csv_export(db, **args)
                artifacts["csv"] = csv_text
                tool_trace.append({"tool": action, "args": args, "csv_bytes": len(csv_text.encode('utf-8'))})
                scratchpad += f"\n- csv_export produced {len(csv_text)} characters of CSV\n"
            elif action == "stats_by_region":
                rows = _tool_stats_by_region(db, **args)
                artifacts["stats_by_region"] = rows
                tool_trace.append({"tool": action, "args": args, "rows": len(rows)})
                scratchpad += f"\n- stats_by_region top5: {rows[:5]}\n"
            elif action == "importance_breakdown":
                rows = _tool_importance_breakdown(db, **args)
                artifacts["importance_breakdown"] = rows
                tool_trace.append({"tool": action, "args": args, "rows": len(rows)})
                scratchpad += f"\n- importance_breakdown: {rows}\n"
            elif action == "heatmap_bins":
                rows = _tool_heatmap_bins(db, **args)
                artifacts["heatmap_bins"] = rows
                tool_trace.append({"tool": action, "args": args, "bins": len(rows)})
                scratchpad += f"\n- heatmap_bins top5: {rows[:5]}\n"
            elif action == "qc_summary":
                if not feature_enabled("qc"):
                    raise ValueError("QC is disabled by data governance policy.")
                rep = _tool_qc_summary(db)
                artifacts["qc_summary"] = rep
                tool_trace.append({"tool": action, "args": {}, "keys": list(rep.keys())})
                scratchpad += f"\n- qc_summary: {rep}\n"
            elif action == "qc_duplicates_mods_id":
                if not feature_enabled("qc"):
                    raise ValueError("QC is disabled by data governance policy.")
                rows = _tool_qc_duplicates_mods_id(db, **args)
                artifacts["qc_duplicates_mods_id"] = rows
                tool_trace.append({"tool": action, "args": args, "groups": len(rows)})
                scratchpad += f"\n- qc_duplicates_mods_id groups: {rows[:5]}\n"
            elif action == "qc_duplicates_coords":
                if not feature_enabled("qc"):
                    raise ValueError("QC is disabled by data governance policy.")
                rows = _tool_qc_duplicates_coords(db, **args)
                artifacts["qc_duplicates_coords"] = rows
                tool_trace.append({"tool": action, "args": args, "groups": len(rows)})
                scratchpad += f"\n- qc_duplicates_coords groups: {rows[:5]}\n"
            elif action == "qc_outliers":
                if not feature_enabled("qc"):
                    raise ValueError("QC is disabled by data governance policy.")
                rep = _tool_qc_outliers(db, **args)
                artifacts["qc_outliers"] = rep
                tool_trace.append({"tool": action, "args": args, "returned": len((rep or {}).get('sample') or [])})
                scratchpad += f"\n- qc_outliers counts: {(rep or {}).get('counts')}\n"
            elif action == "ogc_items_link":
                if not feature_enabled("ogc"):
                    raise ValueError("OGC API Features is disabled by data governance policy.")
                url = _tool_ogc_items_link(args)
                artifacts["ogc_items_url"] = url
                tool_trace.append({"tool": action, "args": args, "url": url})
                scratchpad += f"\n- ogc_items_link: {url}\n"
            elif action == "publish_layer_instructions":
                if not feature_enabled("ogc"):
                    raise ValueError("OGC API Features is disabled by data governance policy.")
                url = str(args.get("ogc_items_url") or artifacts.get("ogc_items_url") or "").strip()
                if not url:
                    url = _tool_ogc_items_link({})
                instructions = (
                    "QGIS (OGC API Features) quick add:\n"
                    "1) Open QGIS → Data Source Manager\n"
                    "2) Find 'OGC API - Features' (or 'WFS/OGC API Features' depending on QGIS version)\n"
                    f"3) New connection → URL: {url}\n"
                    "4) Connect → choose 'mods_occurrences' → Add\n"
                )
                artifacts["qgis_instructions"] = instructions
                tool_trace.append({"tool": action, "args": {"ogc_items_url": url}, "chars": len(instructions)})
                scratchpad += f"\n- publish_layer_instructions generated {len(instructions)} chars\n"
            elif action == "spatial_query":
                if not feature_enabled("spatial"):
                    raise ValueError("Spatial operations are disabled by data governance policy.")
                rep = _tool_spatial_query(db, **args)
                artifacts["spatial_total"] = int(rep.get("total") or 0)
                artifacts["spatial_geojson"] = rep.get("geojson")
                tool_trace.append(
                    {
                        "tool": action,
                        "args": args,
                        "features_count": len((rep.get("geojson") or {}).get("features", [])),
                    }
                )
                scratchpad += f"\n- spatial_query total={rep.get('total')} features={len((rep.get('geojson') or {}).get('features', []))}\n"
            elif action == "spatial_buffer":
                if not feature_enabled("spatial"):
                    raise ValueError("Spatial operations are disabled by data governance policy.")
                rep = _tool_spatial_buffer(db, geometry=args.get("geometry"), distance_m=float(args.get("distance_m")))
                artifacts["spatial_buffer_geometry"] = rep.get("geometry")
                tool_trace.append({"tool": action, "args": args})
                scratchpad += "\n- spatial_buffer produced a buffer geometry\n"
            elif action == "spatial_nearest":
                if not feature_enabled("spatial"):
                    raise ValueError("Spatial operations are disabled by data governance policy.")
                rows = _tool_spatial_nearest(db, **args)
                artifacts["spatial_nearest"] = rows
                tool_trace.append({"tool": action, "args": args, "results_count": len(rows)})
                scratchpad += f"\n- spatial_nearest returned {len(rows)} rows\n"
            elif action == "rag":
                # For Muhanned: rag tool is retrieval-only; LLM response is generated at the end.
                q = str(args.get("query") or user_query)
                ctx, occs = rag_retrieve(q, k=6)
                rag_context = ctx or rag_context
                if occs:
                    last_occurrences = occs
                tool_trace.append({"tool": "rag", "args": {"query": q}, "results_count": len(occs)})
                scratchpad += f"\n- rag_retrieve refreshed context; occs: {len(occs)}\n"
            else:
                # Unknown tool => stop
                tool_trace.append({"tool": "unknown", "raw": action_obj})
            audit_log("agent_unknown_tool", {"query": user_query, "raw": action_obj})
            return sanitize_text(model_out), tool_trace, last_occurrences, artifacts
        except Exception as e:
            tool_trace.append({"tool": action, "args": args, "error": str(e)})
            scratchpad += f"\n- tool {action} errored: {e}\n"

    # If we have artifacts, we can safely produce a deterministic final answer.
    if "geojson" in artifacts:
        features_count = len(artifacts["geojson"].get("features", []))
        audit_log("agent_artifact_geojson", {"query": user_query, "features": features_count})
        return (
            f"Generated GeoJSON FeatureCollection with {features_count} features. "
            f"See `artifacts.geojson` in the response.",
            tool_trace,
            last_occurrences,
            artifacts,
        )
    if "csv" in artifacts:
        audit_log("agent_artifact_csv", {"query": user_query})
        return (
            f"Generated CSV export. See `artifacts.csv` in the response.",
            tool_trace,
            last_occurrences,
            artifacts,
        )
    if "stats_by_region" in artifacts:
        rows = artifacts["stats_by_region"] or []
        top5 = rows[:5]
        lines = [f"{i+1}. {r['admin_region']}: {r['count']}" for i, r in enumerate(top5) if r.get("admin_region")]
        msg = "Top regions by count"
        # Try to infer commodity from the user's query (best-effort)
        if "gold" in user_query.lower():
            msg += " (Gold)"
        msg += ":\n" + ("\n".join(lines) if lines else "(no rows)")
        msg += "\n\nFull table is in `artifacts.stats_by_region`."
        audit_log("agent_artifact_stats_by_region", {"query": user_query, "rows": len(rows)})
        return sanitize_text(msg), tool_trace, last_occurrences, artifacts

    if "importance_breakdown" in artifacts:
        rows = artifacts["importance_breakdown"] or []
        lines = [
            f"- {r.get('occurrence_importance') or 'Unknown'}: {r.get('count')}"
            for r in rows
        ]
        msg = "Occurrence importance breakdown:\n" + ("\n".join(lines) if lines else "(no rows)")
        msg += "\n\nFull breakdown is in `artifacts.importance_breakdown`."
        audit_log("agent_artifact_importance_breakdown", {"query": user_query, "rows": len(rows)})
        return sanitize_text(msg), tool_trace, last_occurrences, artifacts

    if "heatmap_bins" in artifacts:
        bins = artifacts["heatmap_bins"] or []
        preview = bins[:5]
        lines = [f"- ({b['lat']:.4f}, {b['lon']:.4f}): {b['count']}" for b in preview if "lat" in b and "lon" in b]
        msg = f"Generated {len(bins)} heatmap bins. Top 5 bins:\n" + ("\n".join(lines) if lines else "(no bins)")
        msg += "\n\nAll bins are in `artifacts.heatmap_bins`."
        audit_log("agent_artifact_heatmap_bins", {"query": user_query, "bins": len(bins)})
        return sanitize_text(msg), tool_trace, last_occurrences, artifacts

    if "qc_summary" in artifacts:
        rep = artifacts["qc_summary"] or {}
        msg = (
            "QC summary:\n"
            f"- Total rows: {rep.get('total_rows')}\n"
            f"- Missing geom: {rep.get('missing_geom_rows')}\n"
            f"- Null lat: {rep.get('null_latitude_rows')}\n"
            f"- Null lon: {rep.get('null_longitude_rows')}\n"
            f"- Zero coords (0,0): {rep.get('zero_coord_rows')}\n"
            f"- Out of range: {rep.get('out_of_range_rows')}\n"
            f"- Duplicate MODS ID groups: {rep.get('duplicate_mods_id_groups')}\n"
            f"- Duplicate coord groups: {rep.get('duplicate_coord_groups')}\n"
            "\nFull report is in `artifacts.qc_summary`."
        )
        audit_log("agent_artifact_qc_summary", {"query": user_query})
        return sanitize_text(msg), tool_trace, last_occurrences, artifacts

    if "qc_outliers" in artifacts:
        rep = artifacts["qc_outliers"] or {}
        counts = rep.get("counts") or {}
        msg = (
            "QC outliers report:\n"
            f"- invalid_coords: {counts.get('invalid_coords')}\n"
            f"- outside_expected_bbox: {counts.get('outside_expected_bbox')}\n"
            "\nSample rows are in `artifacts.qc_outliers.sample`."
        )
        audit_log("agent_artifact_qc_outliers", {"query": user_query})
        return sanitize_text(msg), tool_trace, last_occurrences, artifacts

    if "ogc_items_url" in artifacts:
        url = str(artifacts.get("ogc_items_url") or "")
        msg = f"OGC API Features items URL (use in QGIS): {url}\n\nAlso see `artifacts.ogc_items_url`."
        audit_log("agent_artifact_ogc_items_url", {"query": user_query})
        return sanitize_text(msg), tool_trace, last_occurrences, artifacts

    if "qgis_instructions" in artifacts:
        msg = str(artifacts.get("qgis_instructions") or "")
        audit_log("agent_artifact_qgis_instructions", {"query": user_query})
        return sanitize_text(msg), tool_trace, last_occurrences, artifacts

    if "spatial_geojson" in artifacts:
        fc = artifacts.get("spatial_geojson") or {}
        features_count = len(fc.get("features", []) if isinstance(fc, dict) else [])
        total = artifacts.get("spatial_total")
        msg = (
            f"Spatial query returned {features_count} features"
            + (f" (total={total})" if total is not None else "")
            + ". See `artifacts.spatial_geojson`."
        )
        audit_log("agent_artifact_spatial_geojson", {"query": user_query, "features": features_count})
        return sanitize_text(msg), tool_trace, last_occurrences, artifacts

    if "spatial_buffer_geometry" in artifacts:
        audit_log("agent_artifact_spatial_buffer", {"query": user_query})
        return (
            "Generated buffer geometry. See `artifacts.spatial_buffer_geometry`.",
            tool_trace,
            last_occurrences,
            artifacts,
        )

    if "spatial_nearest" in artifacts:
        rows = artifacts.get("spatial_nearest") or []
        audit_log("agent_artifact_spatial_nearest", {"query": user_query, "rows": len(rows)})
        return (
            f"Computed {len(rows)} nearest results. See `artifacts.spatial_nearest`.",
            tool_trace,
            last_occurrences,
            artifacts,
        )

    if "nearest_results" in artifacts and not last_occurrences:
        nr = artifacts["nearest_results"] or []
        preview = nr[:5]
        lines = []
        for i, item in enumerate(preview):
            d_m = getattr(item, "distance_m", None) if not isinstance(item, dict) else item.get("distance_m")
            occ_obj = getattr(item, "occurrence", None) if not isinstance(item, dict) else item.get("occurrence")
            if isinstance(occ_obj, OccurrenceInfo):
                name = occ_obj.english_name or occ_obj.mods_id
            else:
                occ = occ_obj or {}
                name = occ.get("english_name") or occ.get("mods_id") or "Unknown"
            if isinstance(d_m, (int, float)):
                lines.append(f"{i+1}. {name} — {d_m/1000:.1f} km")
            else:
                lines.append(f"{i+1}. {name}")
        msg = f"Computed {len(nr)} nearest results. Top 5:\n" + ("\n".join(lines) if lines else "(no results)")
        msg += "\n\nFull list is in `artifacts.nearest_results`."
        audit_log("agent_artifact_nearest_results", {"query": user_query, "rows": len(nr)})
        return sanitize_text(msg), tool_trace, last_occurrences, artifacts

    # Otherwise, force a final answer (either after tool usage or max steps)
    final_prompt = (
        _MUHANNED_PERSONA
        + "\n\nConversation so far:\n"
        + (history_block or "(none)")
        + "\n\nRAG context (from MODS):\n"
        + (rag_context or "(none)")
        + "\n\nUser query:\n"
        + user_query
        + "\n\nTool results so far:\n"
        + (scratchpad or "(none)")
        + "\n\nIMPORTANT: Do NOT call any more tools. Respond with a final JSON object only."
    )
    model_out = generate_response(final_prompt)
    action_obj = _extract_json_object(model_out)
    if action_obj and action_obj.get("action") == "final":
        ans = str(action_obj.get("answer", ""))
        audit_log("agent_final", {"query": user_query})
        return sanitize_text(ans), tool_trace, last_occurrences, artifacts
    audit_log("agent_fallback", {"query": user_query})
    return sanitize_text(model_out), tool_trace, last_occurrences, artifacts

