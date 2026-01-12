from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.dbmodels import Job


def create_job(db: Session, job_type: str, message: str = "") -> Job:
    jid = str(uuid4())
    j = Job(
        id=jid,
        type=job_type,
        status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        progress=0,
        message=message or "",
        result=None,
        error=None,
    )
    db.add(j)
    db.commit()
    db.refresh(j)
    return j


def set_job_status(
    db: Session,
    job_id: str,
    status: str,
    *,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        return
    j.status = status
    j.updated_at = datetime.utcnow()
    if progress is not None:
        j.progress = int(progress)
    if message is not None:
        j.message = message
    if result is not None:
        j.result = result
    if error is not None:
        j.error = error
    db.commit()


def get_job(db: Session, job_id: str) -> Optional[Job]:
    return db.query(Job).filter(Job.id == job_id).first()

