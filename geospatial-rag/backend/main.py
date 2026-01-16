"""
=============================================================================
GEOSPATIAL RAG - MAIN APPLICATION
=============================================================================
FastAPI backend for geospatial mining database RAG system
=============================================================================
"""

import logging
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, HTTPException, UploadFile, File, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from config import settings
from router import get_router, ToolType
from tools import (
    get_sql_generator,
    get_visualizer_2d,
    get_visualizer_3d,
    get_analyzer,
    get_exporter,
    get_voice_io,
)
from llm import get_ollama_client
from database import get_postgis_client

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting Geospatial RAG application...")
    
    # Check connections
    try:
        db = get_postgis_client()
        if db.health_check():
            logger.info("✓ PostGIS database connected")
        else:
            logger.warning("✗ PostGIS database not available")
    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}")
    
    try:
        ollama = get_ollama_client()
        if await ollama.health_check():
            logger.info("✓ Ollama LLM server connected")
        else:
            logger.warning("✗ Ollama LLM server not available")
    except Exception as e:
        logger.error(f"✗ LLM connection failed: {e}")
    
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Geospatial RAG application...")


# =============================================================================
# APPLICATION
# =============================================================================

app = FastAPI(
    title="Geospatial RAG API",
    description="Natural language interface for PostGIS mining database",
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# MODELS
# =============================================================================

class QueryRequest(BaseModel):
    """Natural language query request."""
    query: str = Field(..., description="Natural language query")
    include_visualization: bool = Field(default=False, description="Include visualization data")
    max_results: int = Field(default=100, le=1000, description="Maximum results to return")


class QueryResponse(BaseModel):
    """Query response with data and metadata."""
    success: bool
    tool_used: str
    data: Optional[List[Dict[str, Any]]] = None
    visualization: Optional[Dict[str, Any]] = None
    sql_query: Optional[str] = None
    description: Optional[str] = None
    row_count: Optional[int] = None
    error: Optional[str] = None


class AnalysisRequest(BaseModel):
    """Spatial analysis request."""
    query: str = Field(..., description="Analysis request in natural language")


class ExportRequest(BaseModel):
    """Export request."""
    query: str = Field(..., description="Query for data to export")
    format: str = Field(default="geojson", description="Export format: geojson or shapefile")
    filename: Optional[str] = Field(default=None, description="Custom filename")


class VoiceQueryRequest(BaseModel):
    """Voice query with base64 audio."""
    audio_base64: str = Field(..., description="Base64 encoded audio")
    audio_format: str = Field(default="webm", description="Audio format")


# =============================================================================
# ROUTES
# =============================================================================

@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "endpoints": {
            "query": "/api/query",
            "visualize_2d": "/api/visualize/2d",
            "visualize_3d": "/api/visualize/3d",
            "analyze": "/api/analyze",
            "export": "/api/export",
            "voice": "/api/voice/query",
            "health": "/api/health"
        }
    }


@app.get("/api/health")
async def health_check():
    """Check health of all services."""
    db = get_postgis_client()
    ollama = get_ollama_client()
    
    db_healthy = db.health_check()
    llm_healthy = await ollama.health_check()
    
    return {
        "status": "healthy" if (db_healthy and llm_healthy) else "degraded",
        "services": {
            "database": "healthy" if db_healthy else "unhealthy",
            "llm": "healthy" if llm_healthy else "unhealthy"
        }
    }


# =============================================================================
# MAIN QUERY ENDPOINT (with routing)
# =============================================================================

@app.post("/api/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Main query endpoint with automatic routing.
    
    The router will classify the query and route to the appropriate tool.
    """
    try:
        # Route the query
        router = get_router()
        route_result = await router.route(request.query)
        
        tool = route_result["tool"]
        logger.info(f"Query routed to: {tool.value} (confidence: {route_result['confidence']:.2f})")
        
        # Handle based on tool type
        if tool == ToolType.SQL_QUERY:
            return await _handle_sql_query(request)
        
        elif tool == ToolType.VISUALIZE_2D:
            return await _handle_2d_visualization(request)
        
        elif tool == ToolType.VISUALIZE_3D:
            return await _handle_3d_visualization(request)
        
        elif tool == ToolType.ANALYZE:
            return await _handle_analysis(request)
        
        elif tool == ToolType.EXPORT:
            return await _handle_export_from_query(request)
        
        elif tool == ToolType.GENERAL:
            return await _handle_general(request)
        
        else:
            # Default to SQL query
            return await _handle_sql_query(request)
            
    except Exception as e:
        logger.error(f"Query processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _handle_sql_query(request: QueryRequest) -> QueryResponse:
    """Handle SQL generation and execution."""
    sql_gen = get_sql_generator()
    result = await sql_gen.execute(request.query, request.max_results)
    
    visualization = None
    if request.include_visualization and result.get("success") and result.get("data"):
        viz = get_visualizer_2d()
        visualization = viz.prepare_visualization(result["data"])
    
    return QueryResponse(
        success=result.get("success", False),
        tool_used="sql_query",
        data=result.get("data"),
        visualization=visualization,
        sql_query=result.get("sql_query"),
        description=result.get("description"),
        row_count=result.get("row_count"),
        error=result.get("error")
    )


async def _handle_2d_visualization(request: QueryRequest) -> QueryResponse:
    """Handle 2D map visualization."""
    # First get the data
    sql_gen = get_sql_generator()
    result = await sql_gen.execute(request.query, request.max_results)
    
    if not result.get("success") or not result.get("data"):
        return QueryResponse(
            success=False,
            tool_used="visualize_2d",
            error=result.get("error", "No data to visualize")
        )
    
    # Prepare visualization
    viz = get_visualizer_2d()
    visualization = viz.prepare_visualization(result["data"])
    
    return QueryResponse(
        success=True,
        tool_used="visualize_2d",
        data=result["data"],
        visualization=visualization,
        sql_query=result.get("sql_query"),
        row_count=result.get("row_count")
    )


async def _handle_3d_visualization(request: QueryRequest) -> QueryResponse:
    """Handle 3D CesiumJS visualization."""
    # First get the data
    sql_gen = get_sql_generator()
    result = await sql_gen.execute(request.query, request.max_results)
    
    if not result.get("success") or not result.get("data"):
        return QueryResponse(
            success=False,
            tool_used="visualize_3d",
            error=result.get("error", "No data to visualize")
        )
    
    # Prepare 3D visualization
    viz = get_visualizer_3d()
    visualization = viz.create_3d_config(result["data"])
    
    return QueryResponse(
        success=True,
        tool_used="visualize_3d",
        data=result["data"],
        visualization=visualization,
        sql_query=result.get("sql_query"),
        row_count=result.get("row_count")
    )


async def _handle_analysis(request: QueryRequest) -> QueryResponse:
    """Handle spatial analysis."""
    analyzer = get_analyzer()
    result = await analyzer.analyze(request.query)
    
    # Flatten results for response
    data = []
    for name, res in result.get("results", {}).items():
        if "data" in res:
            data.extend(res["data"])
    
    return QueryResponse(
        success=result.get("success", False),
        tool_used="analyze",
        data=data[:request.max_results] if data else None,
        description=result.get("interpretation"),
        row_count=len(data) if data else 0
    )


async def _handle_export_from_query(request: QueryRequest) -> QueryResponse:
    """Handle export request from natural language."""
    # Determine format from query
    query_lower = request.query.lower()
    format = "geojson"
    if "shapefile" in query_lower or "shp" in query_lower:
        format = "shapefile"
    
    # Get data first
    sql_gen = get_sql_generator()
    result = await sql_gen.execute(request.query, request.max_results)
    
    if not result.get("success") or not result.get("data"):
        return QueryResponse(
            success=False,
            tool_used="export",
            error=result.get("error", "No data to export")
        )
    
    # Export
    exporter = get_exporter()
    export_result = exporter.export(result["data"], format)
    
    return QueryResponse(
        success=export_result.get("success", False),
        tool_used="export",
        description=f"Exported {export_result.get('record_count', 0)} records to {export_result.get('filename', 'file')}",
        row_count=export_result.get("record_count"),
        error=export_result.get("error")
    )


async def _handle_general(request: QueryRequest) -> QueryResponse:
    """Handle general conversation."""
    return QueryResponse(
        success=True,
        tool_used="general",
        description=(
            "I'm a geospatial assistant for the mining database. I can help you:\n\n"
            "• **Search data**: 'Find all gold deposits', 'Show boreholes in region X'\n"
            "• **Visualize on map**: 'Show gold sites on a map'\n"
            "• **3D visualization**: 'Show boreholes in 3D'\n"
            "• **Analyze**: 'Cluster analysis of mineral sites'\n"
            "• **Export**: 'Export copper sites to GeoJSON'\n\n"
            "What would you like to explore?"
        )
    )


# =============================================================================
# DIRECT TOOL ENDPOINTS
# =============================================================================

@app.post("/api/visualize/2d")
async def visualize_2d(request: QueryRequest):
    """Direct 2D visualization endpoint."""
    return await _handle_2d_visualization(request)


@app.post("/api/visualize/3d")
async def visualize_3d(request: QueryRequest):
    """Direct 3D visualization endpoint."""
    return await _handle_3d_visualization(request)


@app.post("/api/analyze")
async def analyze(request: AnalysisRequest):
    """Direct analysis endpoint."""
    analyzer = get_analyzer()
    result = await analyzer.analyze(request.query)
    return result


@app.post("/api/export")
async def export_data(request: ExportRequest):
    """Export query results to file."""
    # Get data
    sql_gen = get_sql_generator()
    result = await sql_gen.execute(request.query, 10000)
    
    if not result.get("success") or not result.get("data"):
        raise HTTPException(status_code=400, detail=result.get("error", "No data"))
    
    # Export
    exporter = get_exporter()
    export_result = exporter.export(result["data"], request.format, request.filename)
    
    if not export_result.get("success"):
        raise HTTPException(status_code=500, detail=export_result.get("error"))
    
    return export_result


@app.get("/api/export/download/{filename}")
async def download_export(filename: str):
    """Download exported file."""
    exporter = get_exporter()
    filepath = os.path.join(exporter.export_dir, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/octet-stream"
    )


# =============================================================================
# VOICE ENDPOINTS
# =============================================================================

@app.post("/api/voice/query")
async def voice_query(request: VoiceQueryRequest):
    """Process voice query."""
    import base64
    
    voice = get_voice_io()
    
    # Decode audio
    try:
        audio_data = base64.b64decode(request.audio_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid audio data: {e}")
    
    # Speech to text
    stt_result = await voice.process_voice_query(audio_data, request.audio_format)
    
    if not stt_result.get("success"):
        return stt_result
    
    # Process the query
    query_request = QueryRequest(query=stt_result["query_text"], include_visualization=True)
    query_result = await process_query(query_request)
    
    # Generate voice response
    response_text = query_result.description or f"Found {query_result.row_count} results."
    tts_result = await voice.speak_response(response_text)
    
    return {
        "transcription": stt_result,
        "query_result": query_result.dict(),
        "voice_response": tts_result
    }


@app.post("/api/voice/tts")
async def text_to_speech(text: str = Query(...), language: str = Query(default="auto")):
    """Convert text to speech."""
    voice = get_voice_io()
    
    if language == "auto":
        result = await voice.speak_response(text)
    else:
        result = await voice.text_to_speech(text, language)
    
    return result


# =============================================================================
# DATABASE INFO ENDPOINTS
# =============================================================================

@app.get("/api/database/tables")
async def get_tables():
    """Get list of database tables."""
    db = get_postgis_client()
    tables = db.get_all_tables()
    
    result = []
    for table in tables:
        count = db.get_table_count(table)
        bounds = db.get_table_bounds(table)
        result.append({
            "name": table,
            "row_count": count,
            "bounds": bounds
        })
    
    return {"tables": result}


@app.get("/api/database/schema/{table_name}")
async def get_table_schema(table_name: str):
    """Get schema for a specific table."""
    db = get_postgis_client()
    schema = db.get_table_schema(table_name)
    return {"table": table_name, "columns": schema}


# =============================================================================
# RUN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
