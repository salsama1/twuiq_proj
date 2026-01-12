from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Dict

from fastapi import APIRouter
from fastapi import HTTPException

from dotenv import load_dotenv

from app.services.governance import audit_log, sanitize_text

router = APIRouter(prefix="/qgis", tags=["qgis"])

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=str(BASE_DIR / ".env"), override=False)

# If the .env file was saved with a UTF-8 BOM, python-dotenv may load keys with a BOM prefix.
# Normalize the most important key so the rest of the app can read it normally.
if "DATABASE_URL" not in os.environ and "\ufeffDATABASE_URL" in os.environ:
    os.environ["DATABASE_URL"] = os.environ.get("\ufeffDATABASE_URL", "")


def _parse_sqlalchemy_url(url: str) -> Dict[str, Any]:
    # Expect: postgresql+psycopg2://user:pass@host:port/dbname
    parsed = urlparse(url)
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname,
        "port": parsed.port,
        "database": (parsed.path or "").lstrip("/") or None,
        "username": parsed.username,
        "password": parsed.password,
    }


@router.get("/connection")
async def qgis_connection_info() -> Dict[str, Any]:
    """
    QGIS helper: how to connect to the PostGIS database.
    For safety, password is omitted unless QGIS_EXPOSE_PASSWORD=1.
    """
    url = (
        os.getenv("DATABASE_URL")
        or os.getenv("\ufeffDATABASE_URL")
        or os.getenv("SQLALCHEMY_DATABASE_URL")
        or os.getenv("\ufeffSQLALCHEMY_DATABASE_URL")
    )
    if not url:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL is not set. Set DATABASE_URL to your PostGIS connection string.",
        )
    info = _parse_sqlalchemy_url(url)
    expose_pw = os.getenv("QGIS_EXPOSE_PASSWORD", "0").lower() in ("1", "true", "yes")
    if not expose_pw:
        info["password"] = None
    info["qgis_layer"] = {
        "schema": "public",
        "table": "mods_occurrences",
        "geometry_column": "geom",
        "geometry_type": "POINT",
        "srid": 4326,
    }
    info["notes"] = [
        "In QGIS: Browser → PostGIS → New Connection",
        "Use Host/Port/Database/Username above, then load table `mods_occurrences` (geom).",
        "You can also load GeoJSON exports from /export/geojson directly.",
    ]
    audit_log("qgis_connection_info", {"expose_password": bool(expose_pw)})
    # extra safety: avoid leaking local paths/tokens in rare cases
    return {k: sanitize_text(str(v)) if isinstance(v, str) else v for k, v in info.items()}


@router.get("/sql-examples")
async def qgis_sql_examples() -> Dict[str, Any]:
    """
    Ready-to-copy SQL snippets for QGIS 'DB Manager' or 'Virtual Layer' workflows.
    """
    payload = {
        "examples": [
            {
                "name": "Gold mines in Riyadh + Makkah",
                "sql": (
                    "SELECT *\n"
                    "FROM mods_occurrences\n"
                    "WHERE major_commodity ILIKE '%Gold%'\n"
                    "  AND (admin_region ILIKE '%Riyadh Region%' OR admin_region ILIKE '%Makkah Region%')\n"
                    "  AND exploration_status ILIKE '%mine%';"
                ),
            },
            {
                "name": "Within 50km of a point (lon/lat)",
                "sql": (
                    "SELECT *\n"
                    "FROM mods_occurrences\n"
                    "WHERE ST_DWithin(\n"
                    "  geom,\n"
                    "  ST_GeogFromText('POINT(46.6753 24.7136)'),\n"
                    "  50000\n"
                    ");"
                ),
            },
        ]
    }
    audit_log("qgis_sql_examples", {"examples": len(payload.get("examples") or [])})
    return payload

