from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Annotated

from app.database import SessionLocal
from app.models.schemas import AgentRequest, AgentResponse, AgentArtifacts
from app.services.master_agent_service import run_master_agent

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
    answer, trace, occs, artifacts = run_master_agent(db, request.query, max_steps=request.max_steps)
    return AgentResponse(response=answer, tool_trace=trace, occurrences=occs, artifacts=AgentArtifacts(**(artifacts or {})))


# Accept both `/agent` and `/agent/` to avoid 405s when an SPA catch-all route exists.
@router.post("", response_model=AgentResponse, include_in_schema=False)
async def agent_endpoint_noslash(request: AgentRequest, db: db_dependency):
    return await agent_endpoint(request, db)

