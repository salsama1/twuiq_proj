from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path


router = APIRouter(tags=["ui"])

BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/ui")
async def ui(request: Request):
    return templates.TemplateResponse("ui.html", {"request": request})

