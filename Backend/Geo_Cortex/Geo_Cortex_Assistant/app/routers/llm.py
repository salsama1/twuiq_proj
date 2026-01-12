from fastapi import APIRouter, HTTPException, status
from app.models.schemas import QueryRequest, QueryResponse
from app.services.router_service import handle_query

query_router = APIRouter(prefix="/query", tags=["llm"])


@query_router.post("/", response_model=QueryResponse)
async def query_llm(request: QueryRequest):
    """RAG-style answer (public; no auth)."""
    try:
        response_text, occurrences = handle_query(request.query)
        return QueryResponse(response=response_text, occurrences=occurrences)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing query: {str(e)}",
        )


@query_router.post("/rag", response_model=QueryResponse)
async def query_rag(request: QueryRequest):
    """RAG query with occurrence extraction (public; no auth)."""
    try:
        response_text, occurrences = handle_query(request.query)
        return QueryResponse(response=response_text, occurrences=occurrences)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing query: {str(e)}"
        )
