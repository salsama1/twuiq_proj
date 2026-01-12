from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List

from app.database import SessionLocal
from app.models.dbmodels import MODSOccurrence


router = APIRouter(prefix="/meta", tags=["meta"])


def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


def _distinct_str(db: Session, col) -> List[str]:
    # Postgres: ORDER BY expressions must appear in SELECT list when using DISTINCT.
    # Use simple ORDER BY col for stability.
    rows = db.query(col).filter(col.isnot(None)).distinct().order_by(col.asc()).all()
    out = []
    for (v,) in rows:
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        out.append(s)
    return out


@router.get("/regions", response_model=List[str])
async def regions(db: Session = Depends(get_db)):
    return _distinct_str(db, MODSOccurrence.admin_region)


@router.get("/commodities", response_model=List[str])
async def commodities(db: Session = Depends(get_db)):
    return _distinct_str(db, MODSOccurrence.major_commodity)


@router.get("/occurrence-types", response_model=List[str])
async def occurrence_types(db: Session = Depends(get_db)):
    return _distinct_str(db, MODSOccurrence.occurrence_type)


@router.get("/exploration-statuses", response_model=List[str])
async def exploration_statuses(db: Session = Depends(get_db)):
    return _distinct_str(db, MODSOccurrence.exploration_status)


@router.get("/importance", response_model=List[str])
async def importance(db: Session = Depends(get_db)):
    return _distinct_str(db, MODSOccurrence.occurrence_importance)

