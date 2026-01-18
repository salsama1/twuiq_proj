import dbmodels as  models
from database import engin, SessionLocal
from fastapi import APIRouter, Depends, HTTPException,Path , FastAPI ,Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from  routers.auth import router as auth_router
from routers.tovists import router as tovisit_router
from routers.llm import query_router as llm_router
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(tags=["tovisit"])

# CORS Middleware
app.add_middleware(CORSMiddleware,
                   allow_origins=["*"],  # Allows all origins
                     allow_credentials=True,
                     allow_methods=["*"],  # Allows all methods
                     allow_headers=["*"],  # Allows all headers
)
# Database Dependency

app.mount("/static", StaticFiles(directory="F:\AI_APPS\Tourist_Assistant\static"), name="static")

models.Base.metadata.create_all(bind=engin)
app.include_router(auth_router)
app.include_router(tovisit_router, tags=["tovisit"])
app.include_router(llm_router, tags=["llmrouter"])


