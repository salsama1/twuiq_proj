from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import occurrences, llm, agent, export, stats, ingest, meta, advanced, qgis, ogc, qc, tiles, spatial, files, jobs, rasters
from app.services.db_maintenance import ensure_postgis_and_indexes
import os
import platform
from uuid import uuid4

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.request_context import set_request_id

# Create database tables
Base.metadata.create_all(bind=engine)
ensure_postgis_and_indexes(engine)

# Initialize FastAPI app
app = FastAPI(
    title="Geo_Cortex_Assistant API",
    description="API for geological occurrence data exploration and management",
    version="1.0.0"
)

# Basic structured-ish logging (stdout). Keep it simple for capstone/demo.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("geocortex")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request correlation IDs (helps debugging + audit log traceability)
class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or str(uuid4())
        set_request_id(rid)
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response


app.add_middleware(RequestIdMiddleware)

# Lightweight access logging with request id + latency
class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        t0 = time.time()
        response = await call_next(request)
        ms = int((time.time() - t0) * 1000)
        rid = response.headers.get("X-Request-Id") or request.headers.get("X-Request-Id")
        logger.info(
            "request method=%s path=%s status=%s ms=%s rid=%s",
            request.method,
            request.url.path,
            response.status_code,
            ms,
            rid,
        )
        return response


app.add_middleware(AccessLogMiddleware)

# Include routers
app.include_router(occurrences.router)
app.include_router(llm.query_router)
app.include_router(agent.router)
app.include_router(export.router)
app.include_router(stats.router)
app.include_router(ingest.router)
app.include_router(meta.router)
app.include_router(advanced.router)
app.include_router(qgis.router)
app.include_router(ogc.router)
app.include_router(qc.router)
app.include_router(tiles.router)
app.include_router(spatial.router)
app.include_router(files.router)
app.include_router(jobs.router)
app.include_router(rasters.router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to Geo_Cortex_Assistant API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.get("/version")
async def version():
    """
    Runtime/build info to confirm what is deployed.
    """
    return {
        "app": "Geo_Cortex_Assistant",
        "version": app.version,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "git_sha": os.getenv("GIT_SHA"),
    }
