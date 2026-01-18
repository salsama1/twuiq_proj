import json
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.schemas import OccurrenceInfo
from app.services.agent_service import run_agent
from app.services.llm_service import generate_response


class ToolType(str, Enum):
    """
    Ported from `geospatial-rag` intent router.
    We use this only for high-level intent classification and then delegate execution to `run_agent`.
    """

    SQL_QUERY = "sql_query"
    VISUALIZE_2D = "visualize_2d"
    VISUALIZE_3D = "visualize_3d"
    ANALYZE = "analyze"
    EXPORT = "export"
    GENERAL = "general"


ROUTER_SYSTEM_PROMPT = """You are an intent classifier for a geospatial mining database system.

Your job is to classify user queries into one of these categories:

1. sql_query - User wants to find, search, count, or list data from the database
2. visualize_2d - User explicitly wants to see data on a 2D map
3. visualize_3d - User explicitly wants 3D visualization
4. analyze - User wants spatial or statistical analysis
5. export - User wants to download/export data as a file
6. general - General questions, greetings, help requests

RULES:
- If a query involves finding data WITHOUT explicit visualization request, choose sql_query
- Only choose visualize_2d or visualize_3d if user EXPLICITLY mentions map/3D/visualization
- Analysis requires analytical keywords (statistics, patterns, clustering, correlation, buffer)
- Export requires download/export/save keywords with file format mentions

Respond with ONLY a JSON object:
{
  "tool": "tool_name",
  "confidence": 0.0-1.0,
  "reason": "brief explanation"
}
"""


def _extract_json_object(text_out: str) -> Optional[Dict[str, Any]]:
    start = text_out.find("{")
    end = text_out.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text_out[start : end + 1])
    except Exception:
        return None


def _quick_classify(query: str) -> Optional[Dict[str, Any]]:
    q = (query or "").lower().strip()
    if not q:
        return {"tool": ToolType.GENERAL, "confidence": 0.95, "reason": "empty query"}

    greetings = ["hello", "hi", "hey", "help", "what can you do", "مرحبا", "السلام"]
    if any(q.startswith(g) for g in greetings) or len(q) < 10:
        return {"tool": ToolType.GENERAL, "confidence": 0.95, "reason": "greeting/short query"}

    # Arabic heuristics (avoid misrouting Arabic data queries to "general")
    # If the query contains Arabic letters and looks like a data request, default to sql_query.
    has_ar = any("\u0600" <= ch <= "\u06FF" for ch in q)
    if has_ar:
        ar_map = ["خريطة", "على الخريطة", "اعرض على الخريطة", "عرض على الخريطة"]
        if any(kw in q for kw in ar_map):
            return {"tool": ToolType.VISUALIZE_2D, "confidence": 0.9, "reason": "arabic map keyword"}
        ar_data = [
            "نقاط",
            "مواقع",
            "تواجد",
            "السعود",
            "المملكة",
            "ذهب",
            "نحاس",
            "فضة",
            "حديد",
            "فوسفات",
            "اظهر",
            "اعرض",
            "جميع",
            "كل",
        ]
        if any(kw in q for kw in ar_data):
            return {"tool": ToolType.SQL_QUERY, "confidence": 0.9, "reason": "arabic data keyword"}

    if any(kw in q for kw in ["3d", "three dimension", "cesium", "terrain view", "terrain"]):
        return {"tool": ToolType.VISUALIZE_3D, "confidence": 0.9, "reason": "3d keyword"}

    map_keywords = ["show on map", "on a map", "plot on map", "display map", "map view", "map"]
    if any(kw in q for kw in map_keywords):
        return {"tool": ToolType.VISUALIZE_2D, "confidence": 0.9, "reason": "map keyword"}

    export_keywords = ["export", "download", "save as", "shapefile", "geojson", "shp"]
    if any(kw in q for kw in export_keywords):
        return {"tool": ToolType.EXPORT, "confidence": 0.9, "reason": "export keyword"}

    analysis_keywords = ["analyze", "analysis", "cluster", "pattern", "statistics", "correlation", "buffer", "density", "distribution"]
    if any(kw in q for kw in analysis_keywords):
        return {"tool": ToolType.ANALYZE, "confidence": 0.85, "reason": "analysis keyword"}

    return None


def classify_intent(query: str) -> Dict[str, Any]:
    quick = _quick_classify(query)
    if quick:
        return {"tool": quick["tool"], "confidence": quick["confidence"], "reason": quick["reason"]}

    # LLM classification fallback (we embed the "system prompt" into the prompt text)
    raw = generate_response(
        ROUTER_SYSTEM_PROMPT
        + "\n\n"
        + f'Classify this query: "{query}"\n\nRespond with JSON only.'
    )
    obj = _extract_json_object(raw) or {}
    tool_str = str(obj.get("tool") or ToolType.SQL_QUERY.value)
    if tool_str not in {t.value for t in ToolType}:
        tool_str = ToolType.SQL_QUERY.value
    return {
        "tool": ToolType(tool_str),
        "confidence": float(obj.get("confidence", 0.7)),
        "reason": str(obj.get("reason", "llm")),
    }


def run_master_agent(
    db: Session, user_query: str, max_steps: int = 3
) -> Tuple[str, List[Dict[str, Any]], Optional[List[OccurrenceInfo]], Dict[str, Any]]:
    """
    "Main agent" (ported conceptually from `geospatial-rag`) that first routes intent,
    then delegates actual execution to the existing tool-loop agent (`run_agent`).
    """
    route = classify_intent(user_query)
    tool = route["tool"]
    trace: List[Dict[str, Any]] = [
        {"tool": "intent_router", "args": {"query": user_query}, "raw": {"tool": getattr(tool, "value", str(tool)), "confidence": route.get("confidence"), "reason": route.get("reason")}}
    ]

    if tool == ToolType.GENERAL:
        msg = (
            "I can help you explore the MODS dataset.\n\n"
            "Try:\n"
            "- \"Show gold occurrences in Riyadh\"\n"
            "- \"Generate heatmap bins for copper occurrences\"\n"
            "- \"Importance breakdown for gold\"\n"
        )
        return msg, trace, None, {}

    # Delegate to the existing agent which produces `occurrences` + `artifacts` used by the UI.
    answer, tool_trace, occs, artifacts = run_agent(db, user_query, max_steps=max_steps)
    return answer, trace + tool_trace, occs, artifacts

