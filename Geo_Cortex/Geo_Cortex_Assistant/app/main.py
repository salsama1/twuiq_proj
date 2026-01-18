from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from app.database import engine, Base
from app.routers import occurrences, llm, agent, export, stats, ui, files, rasters, jobs, speech
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import os

# Load environment variables from a local .env file (if present).
# This makes optional services like /speech easier to configure on Windows.
load_dotenv()

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title="Geo_Cortex_Assistant API",
    description="API for geological occurrence data exploration and management",
    version="1.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(occurrences.router)
app.include_router(llm.query_router)
app.include_router(agent.router)
app.include_router(export.router)
app.include_router(stats.router)
app.include_router(ui.router)
app.include_router(files.router)
app.include_router(rasters.router)
app.include_router(jobs.router)
app.include_router(speech.router)

# Serve UI static assets
BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Optional: Serve the React/Vite frontend build if present.
# This repo layout typically has `frontend/dist` at the integration root.
INTEGRATION_ROOT = BASE_DIR.parents[2] if len(BASE_DIR.parents) >= 3 else None
DEFAULT_FRONTEND_DIST = (INTEGRATION_ROOT / "frontend" / "dist") if INTEGRATION_ROOT else None
FRONTEND_DIST_DIR = Path(os.environ.get("FRONTEND_DIST_DIR", str(DEFAULT_FRONTEND_DIST) if DEFAULT_FRONTEND_DIST else ""))
FRONTEND_INDEX = FRONTEND_DIST_DIR / "index.html" if str(FRONTEND_DIST_DIR) else None
FRONTEND_ENABLED = bool(FRONTEND_INDEX and FRONTEND_INDEX.exists())


@app.get("/")
async def root():
    """Root endpoint"""
    if FRONTEND_ENABLED and FRONTEND_INDEX is not None:
        return FileResponse(str(FRONTEND_INDEX))
    return {"message": "Welcome to Geo_Cortex_Assistant API", "version": "1.0.0", "docs": "/docs"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    """
    SPA fallback for the built frontend.

    - If a static file exists in `frontend/dist`, serve it.
    - Otherwise, serve `index.html` (client-side routing).

    This route is defined last, so it won't shadow API endpoints.
    """
    if not FRONTEND_ENABLED or FRONTEND_INDEX is None:
        # No frontend build to serve; let FastAPI's default 404 happen.
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")

    candidate = FRONTEND_DIST_DIR / full_path
    if full_path and candidate.exists() and candidate.is_file():
        return FileResponse(str(candidate))
    return FileResponse(str(FRONTEND_INDEX))
