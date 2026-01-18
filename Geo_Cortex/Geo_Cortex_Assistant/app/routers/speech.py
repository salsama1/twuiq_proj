from __future__ import annotations

import os
from typing import Any, Dict, Optional, Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.governance import audit_log, feature_enabled, sanitize_text
from app.services.speech_service import process_audio_upload, process_text


router = APIRouter(prefix="/speech", tags=["speech"])


def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]


@router.post("/process")
async def speech_process(
    db: db_dependency,
    audio: UploadFile = File(...),
    voice: str = Form("ar-XA-Wavenet-B"),
    return_audio_base64: str = Form("true"),
    max_steps: int = Form(3),
) -> Dict[str, Any]:
    """
    Arabic audio -> Whisper translate (AR->EN) -> GeoCortex agent -> Arabic text + optional MP3 audio (base64).

    Optional deps required:
    - whisper (+ torch + ffmpeg)
    - google-cloud-translate, google-cloud-texttospeech (+ credentials)
    """
    if not feature_enabled("speech"):
        raise HTTPException(status_code=403, detail="Speech endpoints are disabled by data governance policy.")

    try:
        data = await audio.read()
        resp = await process_audio_upload(
            db,
            data,
            audio.filename or "audio.wav",
            voice=voice,
            return_audio_base64=(str(return_audio_base64).lower() == "true"),
            max_steps=int(max_steps),
        )
        details: Dict[str, Any] = {"filename": audio.filename, "bytes": len(data), "voice": voice}

        # Optional: include transcript in audit logs (off by default).
        # Enable by setting SPEECH_LOG_TRANSCRIPT=1 in backend env/.env.
        if os.getenv("SPEECH_LOG_TRANSCRIPT", "0").lower() in ("1", "true", "yes", "on"):
            stt = sanitize_text(str(resp.get("stt_english") or ""))
            if stt:
                details["stt_english"] = stt[:500]
        audit_log("speech_process", details)
        return resp
    except RuntimeError as e:
        # Missing optional deps / config => 503
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/text")
async def speech_text(
    db: db_dependency,
    text: str = Form(...),
    voice: str = Form("ar-XA-Wavenet-B"),
    return_audio_base64: str = Form("true"),
    max_steps: int = Form(3),
) -> Dict[str, Any]:
    """
    Text (English) -> GeoCortex agent -> Arabic text + optional MP3 audio (base64).
    """
    if not feature_enabled("speech"):
        raise HTTPException(status_code=403, detail="Speech endpoints are disabled by data governance policy.")

    try:
        resp = process_text(
            db,
            text,
            voice=voice,
            return_audio_base64=(str(return_audio_base64).lower() == "true"),
            max_steps=int(max_steps),
        )
        audit_log("speech_text", {"chars": len(text or ""), "voice": voice})
        return resp
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

