import json
from typing import Any, Dict, List, Optional, Tuple
import os
import math

from sqlalchemy.orm import Session
from sqlalchemy import func

from geoalchemy2.functions import ST_DWithin, ST_GeogFromText, ST_Distance

from app.database import IS_POSTGIS
from app.models.dbmodels import MODSOccurrence
from app.models.schemas import OccurrenceInfo, NearestResult
from app.services.llm_service import generate_response
from app.services.router_service import handle_query


_AGENT_INSTRUCTIONS = """You are GeoCortex, an agentic RAG assistant for the MODS dataset.

You can either:
1) Answer directly, or
2) Call a tool to fetch/compute data before answering.

TOOL CALL FORMAT (respond with JSON ONLY):
{"action": "<tool_name>", "args": { ... }}

When you are ready to answer:
{"action": "final", "answer": "<your answer>"}

Available tools:
- search_mods: args {commodity?: str, region?: str, occurrence_type?: str, limit?: int}
- nearby_mods: args {lat: float, lon: float, radius_km: float, limit?: int, commodity?: str}
- bbox_mods: args {min_lat: float, min_lon: float, max_lat: float, max_lon: float, limit?: int, commodity?: str}
- nearest_mods: args {lat: float, lon: float, limit?: int, commodity?: str}
- geojson_export: args {commodity?: str, region?: str, occurrence_type?: str, lat?: float, lon?: float, radius_km?: float, limit?: int}
- csv_export: args {commodity?: str, region?: str, occurrence_type?: str, lat?: float, lon?: float, radius_km?: float, limit?: int}
- stats_by_region: args {commodity?: str, occurrence_type?: str, limit?: int, min_lat?: float, min_lon?: float, max_lat?: float, max_lon?: float}
- stats_by_type: args {commodity?: str, region?: str, limit?: int, min_lat?: float, min_lon?: float, max_lat?: float, max_lon?: float}
- stats_region_by_type: args {commodity?: str, limit?: int, min_lat?: float, min_lon?: float, max_lat?: float, max_lon?: float}
- importance_breakdown: args {commodity?: str, region?: str, occurrence_type?: str}
- heatmap_bins: args {commodity?: str, region?: str, occurrence_type?: str, bin_km?: float, limit?: int}
- commodity_stats: args {region?: str, occurrence_type?: str, limit?: int}
- rag: args {query: str}

Rules:
- If the user asks for data (counts, lists, nearby, filters), call a tool first.
- Keep limits small by default (<= 25) unless user explicitly asks.
- If you call a tool, you must use its results in your final answer.

City coordinate hints (Saudi Arabia) for "near/within Xkm of <city>":
- Riyadh: lat 24.7136, lon 46.6753
- Jeddah: lat 21.4858, lon 39.1925
- Makkah/Mecca: lat 21.4225, lon 39.8262
- Madinah/Medina: lat 24.5247, lon 39.5692
- Dammam: lat 26.4207, lon 50.0888

Saudi Arabia bbox (approx) for country-wide questions ("in Saudi Arabia"):
- min_lon 34.0, min_lat 16.0, max_lon 56.0, max_lat 33.0

Notes:
- The field `occurrence_type` in MODS is typically values like: "Metallic", "Non Metallic", "Metallic and Non Metallic".
- Do NOT pass "Occurrence(s)" as occurrence_type. If user says "occurrences", ignore that field.
"""


_IGNORE_OCCURRENCE_TYPE_VALUES = {"occurrence", "occurrences", "all", "any", "none", "null"}


def _grounded_nl_summary(
    user_query: str,
    tool_trace: List[Dict[str, Any]],
    last_occurrences: Optional[List[OccurrenceInfo]],
    artifacts: Dict[str, Any],
) -> str:
    """
    Force the LLM to produce a natural-language response grounded in tool outputs.
    We provide a small, explicit facts section and instruct the model to only use it.
    """
    occs = last_occurrences or []
    occ_preview = [
        {
            "mods_id": o.mods_id,
            "english_name": o.english_name,
            "major_commodity": o.major_commodity,
            "admin_region": o.admin_region,
            "latitude": o.latitude,
            "longitude": o.longitude,
        }
        for o in occs[:8]
    ]

    facts = {
        "occurrences_count": len(occs),
        "occurrences_preview": occ_preview,
        "has_geojson": bool(artifacts.get("geojson")),
        "has_csv": bool(artifacts.get("csv")),
        "stats_by_region_rows": len(artifacts.get("stats_by_region") or []),
        "importance_breakdown_rows": len(artifacts.get("importance_breakdown") or []),
        "heatmap_bins_count": len(artifacts.get("heatmap_bins") or []),
        "nearest_results_count": len(artifacts.get("nearest_results") or []),
    }

    instructions = (
        "You are a helpful geospatial assistant.\n"
        "Write a short natural-language answer grounded ONLY in the FACTS JSON.\n"
        "Rules:\n"
        "- If occurrences_count > 0, you MUST say you found results (do NOT say 'none found').\n"
        "- If occurrences_count == 0, say no matching occurrences were found.\n"
        "- Prefer 2-5 sentences.\n"
        "- If occurrences_count > 0, include up to 5 example names (english_name) from the preview.\n"
        "- Do not mention internal tool names.\n"
    )

    prompt = (
        instructions
        + "\nUser query:\n"
        + user_query
        + "\n\nFACTS JSON:\n"
        + json.dumps(facts, ensure_ascii=False)
        + "\n\nAnswer:\n"
    )

    txt = generate_response(prompt).strip()

    # Hard guardrail to avoid contradictions.
    if len(occs) > 0:
        txt = txt.rstrip() + f"\n\nFound {len(occs)} occurrences (see table/map)."
    return txt


def _normalize_occurrence_type(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    if v.lower() in _IGNORE_OCCURRENCE_TYPE_VALUES:
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


def _tool_search_mods(
    db: Session,
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    limit: int = 25,
) -> List[OccurrenceInfo]:
    q = db.query(MODSOccurrence)
    if commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    if region:
        q = q.filter(MODSOccurrence.admin_region.ilike(f"%{region}%"))
    if occurrence_type:
        q = q.filter(MODSOccurrence.occurrence_type.ilike(f"%{occurrence_type}%"))
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

    # PostGIS path (fast + accurate)
    if IS_POSTGIS:
        point = ST_GeogFromText(f"POINT({lon} {lat})")
        q = q.filter(ST_DWithin(MODSOccurrence.geom, point, radius_km * 1000.0))
        return [_to_occurrence_info(o) for o in q.limit(limit).all()]

    # SQLite fallback: bbox filter then Haversine distance on lat/lon columns.
    # This keeps the app usable without PostGIS.
    radius_km = float(radius_km)
    lat0 = float(lat)
    lon0 = float(lon)
    if radius_km <= 0:
        return []

    # degrees per km approximations
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(0.1, math.cos(math.radians(lat0))))

    q = q.filter(
        MODSOccurrence.latitude.isnot(None),
        MODSOccurrence.longitude.isnot(None),
        MODSOccurrence.latitude >= (lat0 - dlat),
        MODSOccurrence.latitude <= (lat0 + dlat),
        MODSOccurrence.longitude >= (lon0 - dlon),
        MODSOccurrence.longitude <= (lon0 + dlon),
    )

    # pull a bit more than limit then refine by exact distance
    candidates = q.limit(max(200, limit * 10)).all()

    def haversine_km(a_lat: float, a_lon: float) -> float:
        r = 6371.0
        dphi = math.radians(a_lat - lat0)
        dl = math.radians(a_lon - lon0)
        phi1 = math.radians(lat0)
        phi2 = math.radians(a_lat)
        h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(math.sqrt(h))

    filtered: List[Tuple[float, MODSOccurrence]] = []
    for occ in candidates:
        if occ.latitude is None or occ.longitude is None:
            continue
        d = haversine_km(float(occ.latitude), float(occ.longitude))
        if d <= radius_km:
            filtered.append((d, occ))

    filtered.sort(key=lambda t: t[0])
    return [_to_occurrence_info(o) for _, o in filtered[:limit]]


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
    lat0 = float(lat)
    lon0 = float(lon)

    # PostGIS path
    if IS_POSTGIS:
        point = ST_GeogFromText(f"POINT({lon0} {lat0})")
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

    # SQLite fallback: compute distances client-side.
    q = db.query(MODSOccurrence).filter(
        MODSOccurrence.latitude.isnot(None),
        MODSOccurrence.longitude.isnot(None),
    )
    if commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))

    rows = q.all()

    def haversine_m(a_lat: float, a_lon: float) -> float:
        r = 6371000.0
        dphi = math.radians(a_lat - lat0)
        dl = math.radians(a_lon - lon0)
        phi1 = math.radians(lat0)
        phi2 = math.radians(a_lat)
        h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(math.sqrt(h))

    scored: List[Tuple[float, MODSOccurrence]] = []
    for occ in rows:
        try:
            d = haversine_m(float(occ.latitude), float(occ.longitude))
        except Exception:
            continue
        scored.append((d, occ))

    scored.sort(key=lambda t: t[0])
    out: List[NearestResult] = []
    for d, occ in scored[:limit]:
        out.append(NearestResult(distance_m=float(d), occurrence=_to_occurrence_info(occ)))
    return out


def _tool_geojson_export(
    db: Session,
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: Optional[float] = None,
    limit: int = 25,
) -> Dict[str, Any]:
    q = db.query(MODSOccurrence)
    if commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    if region:
        q = q.filter(MODSOccurrence.admin_region.ilike(f"%{region}%"))
    occurrence_type = _normalize_occurrence_type(occurrence_type)
    if occurrence_type:
        q = q.filter(MODSOccurrence.occurrence_type.ilike(f"%{occurrence_type}%"))
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
        q = q.filter(MODSOccurrence.admin_region.ilike(f"%{region}%"))
    occurrence_type = _normalize_occurrence_type(occurrence_type)
    if occurrence_type:
        q = q.filter(MODSOccurrence.occurrence_type.ilike(f"%{occurrence_type}%"))
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
    min_lat: Optional[float] = None,
    min_lon: Optional[float] = None,
    max_lat: Optional[float] = None,
    max_lon: Optional[float] = None,
) -> List[Dict[str, Any]]:
    q = db.query(MODSOccurrence.admin_region, func.count(MODSOccurrence.id).label("count"))
    if commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    occurrence_type = _normalize_occurrence_type(occurrence_type)
    if occurrence_type:
        q = q.filter(MODSOccurrence.occurrence_type.ilike(f"%{occurrence_type}%"))
    if min_lat is not None and min_lon is not None and max_lat is not None and max_lon is not None:
        q = q.filter(
            MODSOccurrence.latitude >= float(min_lat),
            MODSOccurrence.latitude <= float(max_lat),
            MODSOccurrence.longitude >= float(min_lon),
            MODSOccurrence.longitude <= float(max_lon),
        )
    q = q.group_by(MODSOccurrence.admin_region).order_by(func.count(MODSOccurrence.id).desc()).limit(limit)
    return [{"admin_region": r, "count": int(c)} for r, c in q.all()]


def _tool_stats_by_type(
    db: Session,
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    limit: int = 25,
    min_lat: Optional[float] = None,
    min_lon: Optional[float] = None,
    max_lat: Optional[float] = None,
    max_lon: Optional[float] = None,
) -> List[Dict[str, Any]]:
    q = db.query(MODSOccurrence.occurrence_type, func.count(MODSOccurrence.id).label("count"))
    if commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    if region:
        q = q.filter(MODSOccurrence.admin_region.ilike(f"%{region}%"))
    if min_lat is not None and min_lon is not None and max_lat is not None and max_lon is not None:
        q = q.filter(
            MODSOccurrence.latitude >= float(min_lat),
            MODSOccurrence.latitude <= float(max_lat),
            MODSOccurrence.longitude >= float(min_lon),
            MODSOccurrence.longitude <= float(max_lon),
        )
    q = q.group_by(MODSOccurrence.occurrence_type).order_by(func.count(MODSOccurrence.id).desc()).limit(limit)
    return [{"occurrence_type": t, "count": int(c)} for t, c in q.all()]


def _tool_stats_region_by_type(
    db: Session,
    commodity: Optional[str] = None,
    limit: int = 50,
    min_lat: Optional[float] = None,
    min_lon: Optional[float] = None,
    max_lat: Optional[float] = None,
    max_lon: Optional[float] = None,
) -> List[Dict[str, Any]]:
    q = db.query(
        MODSOccurrence.admin_region,
        MODSOccurrence.occurrence_type,
        func.count(MODSOccurrence.id).label("count"),
    )
    if commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    if min_lat is not None and min_lon is not None and max_lat is not None and max_lon is not None:
        q = q.filter(
            MODSOccurrence.latitude >= float(min_lat),
            MODSOccurrence.latitude <= float(max_lat),
            MODSOccurrence.longitude >= float(min_lon),
            MODSOccurrence.longitude <= float(max_lon),
        )
    q = (
        q.group_by(MODSOccurrence.admin_region, MODSOccurrence.occurrence_type)
        .order_by(func.count(MODSOccurrence.id).desc())
        .limit(limit)
    )
    return [{"admin_region": r, "occurrence_type": t, "count": int(c)} for r, t, c in q.all()]


def _tool_importance_breakdown(
    db: Session,
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    q = db.query(MODSOccurrence.occurrence_importance, func.count(MODSOccurrence.id).label("count"))
    if commodity:
        q = q.filter(MODSOccurrence.major_commodity.ilike(f"%{commodity}%"))
    if region:
        q = q.filter(MODSOccurrence.admin_region.ilike(f"%{region}%"))
    occurrence_type = _normalize_occurrence_type(occurrence_type)
    if occurrence_type:
        q = q.filter(MODSOccurrence.occurrence_type.ilike(f"%{occurrence_type}%"))
    q = q.group_by(MODSOccurrence.occurrence_importance).order_by(func.count(MODSOccurrence.id).desc())
    return [{"occurrence_importance": imp, "count": int(c)} for imp, c in q.all()]


def _tool_heatmap_bins(
    db: Session,
    commodity: Optional[str] = None,
    region: Optional[str] = None,
    occurrence_type: Optional[str] = None,
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
        q = q.filter(MODSOccurrence.admin_region.ilike(f"%{region}%"))
    occurrence_type = _normalize_occurrence_type(occurrence_type)
    if occurrence_type:
        q = q.filter(MODSOccurrence.occurrence_type.ilike(f"%{occurrence_type}%"))
    q = q.group_by(lon_bin, lat_bin).order_by(func.count(MODSOccurrence.id).desc()).limit(limit)
    return [{"lon": float(lon), "lat": float(lat), "count": int(c)} for lon, lat, c in q.all()]


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """
    Best-effort extraction of a JSON object from model output.
    Some local models wrap JSON in prose; this finds the first {...} block.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except Exception:
        return None


def run_agent(
    db: Session, user_query: str, max_steps: int = 3
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

    def _strip_arabic_diacritics(s: str) -> str:
        """
        Remove Arabic harakat/diacritics so keyword matching works for inputs like: جَمِيع vs جميع.
        Also removes tatweel (kashida).
        """
        if not s:
            return s
        out = []
        for ch in s:
            cp = ord(ch)
            # Tatweel
            if cp == 0x0640:
                continue
            # Harakat / diacritics (common ranges)
            if (0x064B <= cp <= 0x065F) or (cp == 0x0670) or (0x06D6 <= cp <= 0x06ED):
                continue
            out.append(ch)
        return "".join(out)

    # --- Deterministic routing for common "dashboard" queries (reduces LLM misrouting) ---
    ql = _strip_arabic_diacritics(user_query.lower())
    SAUDI_BBOX = {"min_lon": 34.0, "min_lat": 16.0, "max_lon": 56.0, "max_lat": 33.0}
    common_commodities = ["gold", "copper", "silver", "zinc", "lead", "iron", "phosphate", "nickel"]
    # Arabic -> English commodity hints (DB values are English)
    ar_commodity_map = {
        "ذهب": "gold",
        "الذهب": "gold",
        "دهب": "gold",
        "الدهب": "gold",
        "نحاس": "copper",
        "فضة": "silver",
        "الفضة": "silver",
        "حديد": "iron",
        "الحديد": "iron",
        "فوسفات": "phosphate",
        "نيكل": "nickel",
        "رصاص": "lead",
        "زنك": "zinc",
    }

    # Arabic region/city hints -> English-ish names that match MODS `admin_region` (via ILIKE)
    ar_region_map = {
        "الرياض": "Riyadh",
        "جدة": "Jeddah",
        "مكة": "Makkah",
        "مكه": "Makkah",
        "المدينة": "Madinah",
        "المدينه": "Madinah",
        "الدمام": "Dammam",
        "تبوك": "Tabouk",
        "عسير": "Asir",
        "جازان": "Jizan",
        "جيزان": "Jizan",
        "القصيم": "Qassim",
        "حائل": "Hail",
        "حايل": "Hail",
        "نجران": "Najran",
        "الباحة": "Bahah",
        "الباحه": "Bahah",
        "مكة المكرمة": "Makkah",
        "المدينة المنورة": "Madinah",
    }

    def _extract_commodity() -> Optional[str]:
        for c in common_commodities:
            if c in ql:
                return c
        for ar, en in ar_commodity_map.items():
            if ar in ql:
                return en
        return None

    def _extract_region_hint() -> Optional[str]:
        # English first (if present)
        if "riyadh" in ql:
            return "Riyadh"
        for ar, en in ar_region_map.items():
            if ar in ql:
                return en
        return None

    # English + Arabic hints for Saudi Arabia
    in_saudi = (
        ("saudi" in ql)
        or ("ksa" in ql)
        or ("saudi arabia" in ql)
        or ("السعود" in ql)  # السعودية / السعوديه / السعودي...
        or ("المملكة العربية السعودية" in ql)
        or ("المملكة" in ql)
    )
    commodity_hint = _extract_commodity()
    region_hint = _extract_region_hint()

    # "all" intent in English + Arabic (جميع/كل/كافة...)
    wants_all = (
        ("all" in ql)
        or ("everything" in ql)
        or ("جميع" in ql)
        or ("كل" in ql)
        or ("كافة" in ql)
        or ("كلها" in ql)
        or ("كامل" in ql)
    )

    # "occurrences/points" intent in English + Arabic
    wants_points = (
        ("occ" in ql)  # tolerate typos like "occarances"
        or ("occurrence" in ql)
        or ("occurrences" in ql)
        or ("point" in ql)
        or ("points" in ql)
        or ("نقاط" in ql)
        or ("مواقع" in ql)
        or ("تواجد" in ql)
    )

    # region by type -> stats_region_by_type
    if ("region by type" in ql) or (("region" in ql) and ("type" in ql) and ("by" in ql)):
        args = {"limit": 50}
        if in_saudi:
            args.update(SAUDI_BBOX)
        if commodity_hint:
            args["commodity"] = commodity_hint
        rows = _tool_stats_region_by_type(db, **args)
        artifacts["stats_region_by_type"] = rows
        tool_trace.append({"tool": "stats_region_by_type", "args": args, "rows": len(rows)})
        top = rows[:10]
        lines = [f"{i+1}. {(r.get('admin_region') or 'Unknown')} - {(r.get('occurrence_type') or 'Unknown')}: {r.get('count')}" for i, r in enumerate(top)]
        return ("Top region-by-type pairs by count:\n" + ("\n".join(lines) if lines else "(no rows)")), tool_trace, last_occurrences, artifacts

    # count by type / what types -> stats_by_type (optionally Saudi bbox)
    if ("by type" in ql) or ("types" in ql and "occurrence" in ql) or ("type of occurrence" in ql):
        args: Dict[str, Any] = {"limit": 25}
        if in_saudi:
            args.update(SAUDI_BBOX)
        if commodity_hint:
            args["commodity"] = commodity_hint
        rows = _tool_stats_by_type(db, **args)
        artifacts["stats_by_type"] = rows
        tool_trace.append({"tool": "stats_by_type", "args": args, "rows": len(rows)})
        top = rows[:8]
        lines = [f"{i+1}. {(r.get('occurrence_type') or 'Unknown')}: {r.get('count')}" for i, r in enumerate(top)]
        return ("Top occurrence types:\n" + ("\n".join(lines) if lines else "(no rows)")), tool_trace, last_occurrences, artifacts

    # occurrences in Saudi Arabia -> bbox_mods
    # Be tolerant to typos like "shoe" and queries that omit "show/list".
    # (ensure this doesn't steal "count by type"/"region by type" queries)
    if in_saudi and wants_points and ("count" not in ql) and ("by type" not in ql) and ("region by type" not in ql):
        # Default to a larger number for country-wide queries; user can ask for "all" explicitly.
        limit = 500
        if wants_all:
            # "All" can be large; keep a safety cap to avoid crushing the UI.
            # Default cap tuned for UI rendering.
            limit = int(os.getenv("AGENT_ALL_LIMIT", "5000"))
        args = {**SAUDI_BBOX, "limit": limit}
        if commodity_hint:
            args["commodity"] = commodity_hint
        results = _tool_bbox_mods(db, **args)
        last_occurrences = results
        tool_trace.append({"tool": "bbox_mods", "args": args, "results_count": len(results)})
        msg = _grounded_nl_summary(user_query, tool_trace, last_occurrences, artifacts)
        if (not wants_all) and (len(results) >= limit):
            msg = msg.rstrip() + f"\n\nShowing the first {limit} results (ask for \"all\" / \"جميع\" to fetch more)."
        if wants_all and (len(results) >= limit):
            msg = msg.rstrip() + f"\n\nShowing the first {limit} results (safety cap)."
        return msg, tool_trace, last_occurrences, artifacts

    # Arabic city/region queries like: "اظهر مواقع الذهب في الرياض"
    # If we detect a region hint and user wants points, use search_mods with region + optional commodity.
    if region_hint and wants_points and ("count" not in ql) and ("by type" not in ql) and ("region by type" not in ql):
        limit = 200
        if wants_all:
            limit = int(os.getenv("AGENT_ALL_LIMIT", "5000"))
        args: Dict[str, Any] = {"region": region_hint, "limit": limit}
        if commodity_hint:
            args["commodity"] = commodity_hint
        results = _tool_search_mods(db, **args)
        last_occurrences = results
        tool_trace.append({"tool": "search_mods", "args": args, "results_count": len(results)})
        msg = _grounded_nl_summary(user_query, tool_trace, last_occurrences, artifacts)
        if (not wants_all) and (len(results) >= limit):
            msg = msg.rstrip() + f"\n\nShowing the first {limit} results (ask for \"all\" / \"جميع\" to fetch more)."
        if wants_all and (len(results) >= limit):
            msg = msg.rstrip() + f"\n\nShowing the first {limit} results (safety cap)."
        return msg, tool_trace, last_occurrences, artifacts

    scratchpad = ""
    for _ in range(max_steps):
        prompt = (
            _AGENT_INSTRUCTIONS
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
            return model_out, tool_trace, last_occurrences, artifacts

        action = action_obj.get("action")
        if action == "final":
            # Always produce a grounded natural-language summary from tool results.
            return _grounded_nl_summary(user_query, tool_trace, last_occurrences, artifacts), tool_trace, last_occurrences, artifacts

        args = action_obj.get("args") or {}
        # If we've already produced the artifact for this tool, stop (prevents multi-tool spam).
        already = (
            (action == "heatmap_bins" and "heatmap_bins" in artifacts)
            or (action == "stats_by_region" and "stats_by_region" in artifacts)
            or (action == "importance_breakdown" and "importance_breakdown" in artifacts)
            or (action == "geojson_export" and "geojson" in artifacts)
            or (action == "csv_export" and "csv" in artifacts)
            or (action == "nearest_mods" and "nearest_results" in artifacts)
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
            elif action == "stats_by_type":
                rows = _tool_stats_by_type(db, **args)
                artifacts["stats_by_type"] = rows
                tool_trace.append({"tool": action, "args": args, "rows": len(rows)})
                scratchpad += f"\n- stats_by_type top5: {rows[:5]}\n"
            elif action == "stats_region_by_type":
                rows = _tool_stats_region_by_type(db, **args)
                artifacts["stats_region_by_type"] = rows
                tool_trace.append({"tool": action, "args": args, "rows": len(rows)})
                scratchpad += f"\n- stats_region_by_type top5: {rows[:5]}\n"
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
            elif action == "rag":
                q = str(args.get("query") or user_query)
                resp, occs = handle_query(q)
                last_occurrences = occs
                tool_trace.append({"tool": action, "args": {"query": q}, "results_count": len(occs)})
                scratchpad += f"\n- rag returned {len(occs)} rows; response preview: {resp[:250]}\n"
            else:
                # Unknown tool => stop
                tool_trace.append({"tool": "unknown", "raw": action_obj})
                return model_out, tool_trace, last_occurrences, artifacts
        except Exception as e:
            tool_trace.append({"tool": action, "args": args, "error": str(e)})
            scratchpad += f"\n- tool {action} errored: {e}\n"

    # If we have artifacts, we can safely produce a deterministic final answer.
    if "geojson" in artifacts:
        features_count = len(artifacts["geojson"].get("features", []))
        return (
            f"Generated GeoJSON FeatureCollection with {features_count} features. "
            f"See `artifacts.geojson` in the response.",
            tool_trace,
            last_occurrences,
            artifacts,
        )
    if "csv" in artifacts:
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
        return msg, tool_trace, last_occurrences, artifacts

    if "stats_by_type" in artifacts:
        rows = artifacts["stats_by_type"] or []
        top = rows[:10]
        lines = [f"{i+1}. {(r.get('occurrence_type') or 'Unknown')}: {r.get('count')}" for i, r in enumerate(top)]
        msg = "Top occurrence types:\n" + ("\n".join(lines) if lines else "(no rows)")
        return msg, tool_trace, last_occurrences, artifacts

    if "stats_region_by_type" in artifacts:
        rows = artifacts["stats_region_by_type"] or []
        top = rows[:10]
        lines = [f"{i+1}. {(r.get('admin_region') or 'Unknown')} - {(r.get('occurrence_type') or 'Unknown')}: {r.get('count')}" for i, r in enumerate(top)]
        msg = "Top region-by-type pairs by count:\n" + ("\n".join(lines) if lines else "(no rows)")
        return msg, tool_trace, last_occurrences, artifacts

    if "importance_breakdown" in artifacts:
        rows = artifacts["importance_breakdown"] or []
        lines = [
            f"- {r.get('occurrence_importance') or 'Unknown'}: {r.get('count')}"
            for r in rows
        ]
        msg = "Occurrence importance breakdown:\n" + ("\n".join(lines) if lines else "(no rows)")
        return msg, tool_trace, last_occurrences, artifacts

    if "heatmap_bins" in artifacts:
        bins = artifacts["heatmap_bins"] or []
        preview = bins[:5]
        lines = [f"- ({b['lat']:.4f}, {b['lon']:.4f}): {b['count']}" for b in preview if "lat" in b and "lon" in b]
        msg = f"Generated {len(bins)} heatmap bins. Top 5 bins:\n" + ("\n".join(lines) if lines else "(no bins)")
        return msg, tool_trace, last_occurrences, artifacts

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
        return msg, tool_trace, last_occurrences, artifacts

    # Otherwise, force a final answer (either after tool usage or max steps)
    # If tools ran, summarize grounded in tool results (prevents hallucinations/contradictions).
    if tool_trace or last_occurrences or artifacts:
        return _grounded_nl_summary(user_query, tool_trace, last_occurrences, artifacts), tool_trace, last_occurrences, artifacts

    # No tools ran; return raw model output.
    return model_out, tool_trace, last_occurrences, artifacts

