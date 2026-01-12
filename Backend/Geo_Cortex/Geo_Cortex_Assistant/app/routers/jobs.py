from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.dbmodels import Job
from app.services.governance import audit_log, feature_enabled


router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


@router.get("/{job_id}")
async def get_job(job_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    if not feature_enabled("jobs"):
        raise HTTPException(status_code=403, detail="Jobs API is disabled by data governance policy.")
    j: Optional[Job] = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    audit_log("jobs_get", {"job_id": job_id, "status": j.status})
    return {
        "id": j.id,
        "type": j.type,
        "status": j.status,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "updated_at": j.updated_at.isoformat() if j.updated_at else None,
        "progress": j.progress,
        "message": j.message,
        "result": j.result,
        "error": j.error,
    }

