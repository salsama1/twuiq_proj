from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, BackgroundTasks
from sqlalchemy import text
from sqlalchemy.orm import Session
from geoalchemy2.elements import WKTElement

from app.database import SessionLocal, engine, Base
from app.models.dbmodels import MODSOccurrence

load_dotenv()

router = APIRouter(prefix="/ingest", tags=["ingest"])

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MODS_CSV_PATH = BASE_DIR / "MODS.csv"


def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


def _require_ingest_enabled() -> None:
    enabled = os.getenv("INGEST_ENABLE", "0").lower() in ("1", "true", "yes")
    if not enabled:
        raise HTTPException(
            status_code=403,
            detail="Ingestion is disabled. Set INGEST_ENABLE=1 to enable /ingest endpoints.",
        )


def _validate_mods_columns(df: pd.DataFrame) -> None:
    required = {"MODS", "Longitude", "Latitude", "Major Commodity", "Admin Region"}
    missing = sorted([c for c in required if c not in df.columns])
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"CSV is missing required columns: {missing}. "
            f"Expected MODS schema headers (e.g. 'MODS', 'English Name', 'Arabic Name', ...).",
        )


def _safe_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    s = str(v).strip()
    return s or None


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None or pd.isna(v):
            return None
    except Exception:
        pass
    try:
        return float(v)
    except Exception:
        return None


def _build_occurrence_from_row(row: Dict[str, Any]) -> MODSOccurrence:
    lon = _safe_float(row.get("Longitude"))
    lat = _safe_float(row.get("Latitude"))
    geom = None
    if lon is not None and lat is not None:
        geom = WKTElement(f"POINT({lon} {lat})", srid=4326)

    return MODSOccurrence(
        mods_id=_safe_str(row.get("MODS")) or "",
        english_name=_safe_str(row.get("English Name")) or "",
        arabic_name=_safe_str(row.get("Arabic Name")),
        library_reference=_safe_str(row.get("Library Reference")),
        major_commodity=_safe_str(row.get("Major Commodity")) or "",
        longitude=lon or 0.0,
        latitude=lat or 0.0,
        geom=geom,
        quadrangle=_safe_str(row.get("Quadrangle")),
        admin_region=_safe_str(row.get("Admin Region")),
        elevation=_safe_float(row.get("Elevation")),
        occurrence_type=_safe_str(row.get("Occurrence Type")),
        input_date=_safe_str(row.get("Input Date")),
        last_update=_safe_str(row.get("Last Update")),
        position_origin=_safe_str(row.get("Position Origin")),
        exploration_status=_safe_str(row.get("Exploration Status")),
        security_status=_safe_str(row.get("Security Status")),
        occurrence_importance=_safe_str(row.get("Occurrence Importance")),
        occurrence_status=_safe_str(row.get("Occurrence Status")),
        ancient_workings=_safe_str(row.get("Ancient Workings")),
        geochemical_exploration=_safe_str(row.get("Geochemical Exploration")),
        geophysical_exploration=_safe_str(row.get("Geophysical Exploration")),
        mapping_exploration=_safe_str(row.get("Mapping Exploration")),
        exploration_data=_safe_str(row.get("Exploration Data")),
        structural_province=_safe_str(row.get("Structural Province")),
        regional_structure=_safe_str(row.get("Regional Structure")),
        geologic_group=_safe_str(row.get("Geologic Group")),
        geologic_formation=_safe_str(row.get("Geologic Formation")),
        host_rocks=_safe_str(row.get("Host Rocks")),
        country_rocks=_safe_str(row.get("Country Rocks")),
        geology=_safe_str(row.get("Gitology")) or _safe_str(row.get("Geology")),
        mineralization_control=_safe_str(row.get("Mineralization Control")),
        alteration=_safe_str(row.get("Alteration")),
        mineralization_morphology=_safe_str(row.get("Mineralization Morphology")),
        minor_commodities=_safe_str(row.get("Minor Commodities")),
        trace_commodities=_safe_str(row.get("Trace Commodities")),
    )


def _rebuild_vectorstore_background() -> None:
    # Rebuild uses scripts/build_vectorstore.py which reads BASE_DIR/MODS.csv
    try:
        from scripts.build_vectorstore import build_vectorstore

        build_vectorstore()
    except Exception:
        # swallow errors; user can check logs
        return


@router.post("/mods-csv")
async def ingest_mods_csv(
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    replace_existing: bool = True,
    save_as_mods_csv: bool = True,
    rebuild_vectorstore: bool = False,
    max_rows: int = 200000,
) -> Dict[str, Any]:
    """
    Upload a MODS-format CSV and load it into PostGIS (public, but disabled by default).

    Safety:
    - Disabled unless INGEST_ENABLE=1
    - max_rows guard
    """
    _require_ingest_enabled()

    if file.content_type not in (None, "", "text/csv", "application/vnd.ms-excel"):
        # Browsers sometimes send vnd.ms-excel for CSV
        raise HTTPException(status_code=400, detail=f"Unsupported content-type: {file.content_type}")

    # Read CSV into DataFrame
    try:
        df = pd.read_csv(file.file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {e}")

    if len(df) > max_rows:
        raise HTTPException(status_code=400, detail=f"CSV too large: {len(df)} rows (max_rows={max_rows})")

    _validate_mods_columns(df)

    # Optionally persist as MODS.csv (so vectorstore build and scripts keep working)
    if save_as_mods_csv:
        try:
            df.to_csv(DEFAULT_MODS_CSV_PATH, index=False)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save MODS.csv: {e}")

    # Ensure PostGIS and tables
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(bind=engine)

    if replace_existing:
        db.query(MODSOccurrence).delete()
        db.commit()

    # Bulk insert
    objs = []
    existing_mods_ids = set()
    if not replace_existing:
        try:
            existing_mods_ids = {m for (m,) in db.query(MODSOccurrence.mods_id).all() if m}
        except Exception:
            existing_mods_ids = set()
    rows = df.to_dict(orient="records")
    for r in rows:
        try:
            mid = _safe_str(r.get("MODS")) or ""
            if not mid:
                continue
            if existing_mods_ids and mid in existing_mods_ids:
                continue
            objs.append(_build_occurrence_from_row(r))
        except Exception:
            continue

    try:
        db.bulk_save_objects(objs)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"DB insert failed: {e}")

    if rebuild_vectorstore:
        # Rebuild embeddings can take time; run in background.
        background.add_task(_rebuild_vectorstore_background)

    try:
        from app.services.governance import audit_log

        audit_log(
            "ingest_mods_csv",
            {
                "filename": file.filename,
                "replace_existing": replace_existing,
                "saved_mods_csv": bool(save_as_mods_csv),
                "rows_in_csv": int(len(df)),
                "rows_inserted": int(len(objs)),
                "vectorstore_rebuild_started": bool(rebuild_vectorstore),
            },
        )
    except Exception:
        pass

    return {
        "ok": True,
        "rows_in_csv": int(len(df)),
        "rows_inserted": int(len(objs)),
        "saved_mods_csv": bool(save_as_mods_csv),
        "mods_csv_path": str(DEFAULT_MODS_CSV_PATH) if save_as_mods_csv else None,
        "vectorstore_rebuild_started": bool(rebuild_vectorstore),
    }

