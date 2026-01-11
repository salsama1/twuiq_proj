from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Annotated

from app.database import SessionLocal
from app.models.schemas import AgentRequest, AgentResponse, AgentArtifacts
from app.services.agent_service import run_agent

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
    answer, trace, occs, artifacts = run_agent(db, request.query, max_steps=request.max_steps)
    return AgentResponse(response=answer, tool_trace=trace, occurrences=occs, artifacts=AgentArtifacts(**(artifacts or {})))

