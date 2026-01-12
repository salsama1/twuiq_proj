from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from sqlalchemy.orm import Session
from typing import Annotated

from app.database import SessionLocal
from app.models.schemas import AgentRequest, AgentResponse, AgentArtifacts, WorkflowRequest, WorkflowResponse, WorkflowStep
from app.services.agent_service import run_agent, run_workflow
from app.services.chat_store import (
    get_history_db,
    append_message_db,
    reset_session_db,
    get_state_value_db,
    set_state_value_db,
)
from app.services.geofile_service import parse_geofile, featurecollection_to_union_geometry
from app.services.request_context import set_uploaded_geometry
from uuid import uuid4

router = APIRouter(prefix="/agent", tags=["agent"])


def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]


@router.post("/", response_model=AgentResponse)
async def agent_endpoint(request: AgentRequest, db: db_dependency):
    """
    Agentic RAG endpoint (public; no auth).
    The model can run small "processes" (search/count/nearby) before answering.
    """
    session_id = request.session_id or str(uuid4())
    history = get_history_db(db, session_id)
    append_message_db(db, session_id, "user", request.query)

    answer, trace, occs, artifacts = run_agent(
        db, request.query, max_steps=request.max_steps, chat_history=history
    )
    append_message_db(db, session_id, "assistant", answer)

    return AgentResponse(
        response=answer,
        tool_trace=trace,
        occurrences=occs,
        artifacts=AgentArtifacts(**(artifacts or {})),
        session_id=session_id,
    )


@router.post("/file", response_model=AgentResponse)
async def agent_with_file(
    db: db_dependency,
    query: str = Form(...),
    max_steps: int = Form(3),
    session_id: str | None = Form(None),
    file: UploadFile = File(...),
):
    """
    Agent endpoint that accepts a geospatial file (GeoJSON/KML/GPX/WKT) as context.
    The uploaded geometry is available to spatial tools via a request-scoped reference.
    """
    sid = session_id or str(uuid4())
    history = get_history_db(db, sid)
    append_message_db(db, sid, "user", query)

    try:
        data = await file.read()
        fc = parse_geofile(file.filename or "", file.content_type, data)
        union_geom = featurecollection_to_union_geometry(fc)
        set_uploaded_geometry(union_geom)
        set_state_value_db(db, sid, "last_aoi_geometry", union_geom)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")

    answer, trace, occs, artifacts = run_agent(db, query, max_steps=max_steps, chat_history=history)
    append_message_db(db, sid, "assistant", answer)

    # Include a hint artifact about the uploaded geometry
    artifacts = artifacts or {}
    artifacts.setdefault("extra", {})
    artifacts["extra"]["uploaded_filename"] = file.filename

    return AgentResponse(
        response=answer,
        tool_trace=trace,
        occurrences=occs,
        artifacts=AgentArtifacts(**(artifacts or {})),
        session_id=sid,
    )


@router.post("/workflow", response_model=WorkflowResponse)
async def agent_workflow(request: WorkflowRequest, db: db_dependency):
    """
    Workflow agent: returns an explicit plan and executes it.
    Uses session memory for last AOI if present.
    """
    session_id = request.session_id or str(uuid4())
    history = get_history_db(db, session_id)
    append_message_db(db, session_id, "user", request.query)

    # Load last AOI geometry from session memory, if available
    last_aoi = get_state_value_db(db, session_id, "last_aoi_geometry")
    if isinstance(last_aoi, dict) and last_aoi.get("type"):
        set_uploaded_geometry(last_aoi)

    answer, plan, trace, occs, artifacts = run_workflow(
        db,
        request.query,
        max_steps=request.max_steps,
        use_llm=request.use_llm,
        chat_history=history,
    )
    append_message_db(db, session_id, "assistant", answer)

    plan_models = [WorkflowStep(action=s.get("action", ""), args=s.get("args") or {}, why=s.get("why")) for s in (plan or [])]

    # Update session memory for AOI if workflow created a buffer geometry
    if artifacts and isinstance(artifacts.get("spatial_buffer_geometry"), dict):
        set_state_value_db(db, session_id, "last_aoi_geometry", artifacts.get("spatial_buffer_geometry"))

    return WorkflowResponse(
        response=answer,
        plan=plan_models,
        tool_trace=trace,
        occurrences=occs,
        artifacts=AgentArtifacts(**(artifacts or {})),
        session_id=session_id,
    )


@router.post("/workflow/file", response_model=WorkflowResponse)
async def agent_workflow_with_file(
    db: db_dependency,
    query: str = Form(...),
    max_steps: int = Form(6),
    use_llm: bool = Form(True),
    session_id: str | None = Form(None),
    file: UploadFile = File(...),
):
    """
    Workflow agent + file upload. Stores uploaded geometry into session memory and request context.
    """
    sid = session_id or str(uuid4())
    history = get_history_db(db, sid)
    append_message_db(db, sid, "user", query)

    try:
        data = await file.read()
        fc = parse_geofile(file.filename or "", file.content_type, data)
        union_geom = featurecollection_to_union_geometry(fc)
        set_uploaded_geometry(union_geom)
        set_state_value_db(db, sid, "last_aoi_geometry", union_geom)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")

    answer, plan, trace, occs, artifacts = run_workflow(
        db,
        query,
        max_steps=max_steps,
        use_llm=use_llm,
        chat_history=history,
    )
    append_message_db(db, sid, "assistant", answer)

    artifacts = artifacts or {}
    artifacts.setdefault("extra", {})
    artifacts["extra"]["uploaded_filename"] = file.filename
    plan_models = [WorkflowStep(action=s.get("action", ""), args=s.get("args") or {}, why=s.get("why")) for s in (plan or [])]

    return WorkflowResponse(
        response=answer,
        plan=plan_models,
        tool_trace=trace,
        occurrences=occs,
        artifacts=AgentArtifacts(**(artifacts or {})),
        session_id=sid,
    )


@router.post("/reset")
async def reset_agent(session_id: str):
    # best-effort; session may or may not exist
    db = SessionLocal()
    try:
        reset_session_db(db, session_id)
    finally:
        db.close()
    return {"ok": True, "session_id": session_id}

