from ctypes.wintypes import LONG
import dbmodels 
from database import engin, SessionLocal
from fastapi import APIRouter, Depends, HTTPException,Path , FastAPI ,Request ,Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Annotated
from fastapi.middleware.cors import CORSMiddleware
from fastapi import status
from pydantic import BaseModel , Field 
from enum import Enum
from fastapi.responses import HTMLResponse
from .auth import get_current_user 

from fastapi import APIRouter
from models.schemas import QueryRequest, QueryResponse
from services.router_service import handle_query
from services.router_service import handle_query_with_contex ,handle_chat, handle_query

# for templating and static files
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from starlette.responses import RedirectResponse


# Initialize the router
#router = APIRouter(
#
#)

router = APIRouter(prefix="/auth")

templates = Jinja2Templates(directory=r"F:\AI_APPS\Tourist_Assistant\templates")





def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()
db_dependency =  Annotated[Session, Depends(get_db)]
user_dependency = Annotated[dbmodels.Users, Depends(get_current_user)]


# enums
class CategoryEnum(str, Enum):
    restaurant = "restaurant"
    museum = "museum"
    park = "park"

class PriorityEnum(int, Enum):
    low = 1
    medium = 5
    high = 9

# models 
class TovisitCreate(BaseModel):
    name: str=Field(min_length=3)
    description: str=Field(min_length=3, max_length=100)
    priority:PriorityEnum
    category:CategoryEnum
    Visited: bool
    rating_if_visited: float


def redirect_to_login():
    redirect_response = RedirectResponse(url="/auth/login-page", status_code=status.HTTP_302_FOUND)
    redirect_response.delete_cookie(key="access_token")
    return redirect_response


### Pages ###
@router.get("/tovisit-page")
async def render_todo_page(request: Request, db: db_dependency):
    token = request.cookies.get("access_token")
    user = await get_current_user(token)

    if user is None:
        return redirect_to_login()

    todos = db.query(dbmodels.Tovisit).filter(dbmodels.Tovisit.user_id == user.get("user_id")).all()
    return templates.TemplateResponse("tovisit.html", {"request": request, "todos": todos, "user": user})


@router.get("/chat")
async def chat_page(request: Request):
    return templates.TemplateResponse("auth_chat.html", {"request": request})



from uuid import uuid4

@router.post("/chat-query")
async def chat_query_form(request: Request,db: db_dependency,query: str = Form(...)):
    
    
    print(f"[DEBUG] Received query: {query}")
    token = request.cookies.get("access_token")
    print(f"[DEBUG] Received token: {token}")
    
    user = await get_current_user(token)
    print(f"[DEBUG] User from cookie: {user}")

    if user is None:
        return redirect_to_login()


    user_id = user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID missing")

    try:
        # Call only once
        response_text, places = handle_query(query)
        print(f"[DEBUG] Received places: {places}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query processing failed: {e}")

    returned_places = []

    for p in places:
        try:
            print(f"[DEBUG] Processing place: {p.poi_name}")

            # Ensure UUID is present
            if not hasattr(p, "uuid") or not p.uuid:
                p.uuid = str(uuid4())

            # Check if the place already exists in Places
            db_place = db.query(dbmodels.Places).filter_by(poi_name=p.poi_name).first()

            #if not db_place:
            #    db_place = dbmodels.Places(
            #        uuid=p.uuid,
            #        poi_name=p.poi_name,
            #        lat=p.lat,
            #        lng=p.lng,
            #        category=p.category,
            #        reviews_no=p.reviews_no,
            #        price_range=p.price_range,
            #    )
            #    db.add(db_place)
            #    db.commit()
            #    db.refresh(db_place)
            #    print(f"[INFO] Added new place to DB: {db_place.poi_name}")

            # Check if this place is already in user's Tovisit list
            existing = db.query(dbmodels.Tovisit).filter_by(
                user_id=user_id,
                place_uuid=db_place.uuid
            ).first()

            if not existing:
                tovisit = dbmodels.Tovisit(
                    user_id=user_id,
                    place_uuid=db_place.uuid,
                    name=db_place.poi_name,
                    description=f"""
                    
                    https://www.google.com/maps?q={db_place.lat},{db_place.lng}
                    """,
                    priority=1,
                    category=db_place.category,

                )
                db.add(tovisit)
                db.commit()
                print(f"[INFO] Added to Tovisit: {tovisit.name}")
            else:
                print(f"[SKIP] Already exists in Tovisit: {db_place.poi_name}")

            returned_places.append(p)

        except Exception as e:
            db.rollback()
            print(f"[ERROR] Failed to process {getattr(p, 'poi_name', 'Unknown')}: {e}")

    return templates.TemplateResponse("auth_chat.html", {
        "request": request,
        "query": query,
        "response": response_text,
    })

@router.get("/tovisits/delete/{tovisit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tovisit(request: Request,db: db_dependency, tovisit_id: int):
    token = request.cookies.get("access_token")
    user = await get_current_user(token)

    if user is None:
        return redirect_to_login()
    if user is None :
        raise HTTPException(status_code=401, detail="Authentication Failed")
  
    db_tovisit = db.query(dbmodels.Tovisit).filter(dbmodels.Tovisit.id == tovisit_id)\
        .filter(dbmodels.Tovisit.user_id == user.get('user_id')).first()
    if db_tovisit is None:
        raise HTTPException(status_code=404, detail="Tovisit not found")
    db.delete(db_tovisit)
    db.commit()


    todos = db.query(dbmodels.Tovisit).filter(dbmodels.Tovisit.user_id == user.get("user_id")).all()
    return templates.TemplateResponse("tovisit.html", {"request": request, "todos": todos, "user": user})

### End of Pages ###


#@router.get("/tovisit-page")
#async def render_todo_page(request: Request, db: db_dependency):
#    print("Request method:", request.method)
#    try:
#        user = await get_current_user(request.cookies.get('access_token'))
#
#        if user is None:
#            return redirect_to_login()
#
#        todos = db.query(dbmodels.Tovisit).filter(dbmodels.Tovisit.user_id == user.get("user_id")).all()
#
#        return templates.TemplateResponse("todo.html", {"request": request, "todos": todos, "user": user})
#
#    except:
#        return redirect_to_login()


@router.get('/add-tovisit-page')
async def render_todo_page(request: Request):
    try:
        user = await get_current_user(request.cookies.get('access_token'))

        if user is None:
            return redirect_to_login()

        return templates.TemplateResponse("add-todo.html", {"request": request, "user": user})

    except:
        return redirect_to_login()


@router.get("/edit-tovisit-page/{todo_id}")
async def render_edit_todo_page(request: Request, tovisit_id: int, db: db_dependency):
    try:
        user = await get_current_user(request.cookies.get('access_token'))

        if user is None:
            return redirect_to_login()

        todo = db.query(dbmodels.Tovisit).filter(dbmodels.Tovisit.id == tovisit_id).first()

        return templates.TemplateResponse("edit-todo.html", {"request": request, "todo": todo, "user": user})

    except:
        return redirect_to_login()



### Endpoints ###


# Routes

@router.get("/map/", response_class=HTMLResponse)
async def show_map(request:Request):
    return templates.TemplateResponse("kepler.html", {"request": request, "title": "Restaurants Map"})
###########################################################

from services.router_service import handle_query
from uuid import uuid4
@router.post("/ragquery", response_model=QueryResponse)
async def query_rag(user:user_dependency,db:db_dependency ,request: QueryRequest):
    if user is None :
        raise HTTPException(status_code=401, detail="Authentication Failed")
    user_id = user.get('user_id')
    if user_id is None:
        raise HTTPException(status_code=401, detail="User ID missing")
    response_text, places = handle_query(request.query)

    returned_places = []
    for p in places:
        
        # Check if already exists
        db_place = db.query(dbmodels.Places).filter_by(poi_name=p.poi_name).first()
        print(f"Processing place: {p.poi_name} with UUID: {p.uuid}===========")
        #if not db_place:
        #    db_place = dbmodels.Places(**p.dict())
        #    db.add(db_place)
        #    db.commit()
        #    db.refresh(db_place)

        # Add to Tovisit if not exists
        if not db.query(dbmodels.Tovisit).filter_by(user_id=user_id, place_uuid=db_place.uuid).first():
            tovisit = dbmodels.Tovisit(
                user_id=user_id,
                place_uuid=db_place.uuid,
                name=db_place.poi_name,
                description=f""" Recommended via assistant
                https://www.google.com/maps?q={db_place.lat},{db_place.lng}({db_place.poi_name})
                with rating {db_place.reviews_no} and price_range {db_place.price_range} 
                """,
                priority=1,
                category=db_place.category
            )
            db.add(tovisit)
            db.commit()

        returned_places.append(p)

    return QueryResponse(response=response_text, places=returned_places)
###########################################################
@router.get("/tovisits/")
async def read_all( user:user_dependency,db:db_dependency ,skip: int = 0, limit: int = 100):
    if user is None :
        raise HTTPException(status_code=401, detail="Authentication Failed")
    tovisit = db.query(dbmodels.Tovisit).filter(dbmodels.Tovisit.user_id == user.get('user_id')).all()
    return tovisit

@router.get("/tovisits/{tovisit_id}",status_code=status.HTTP_200_OK)
async def read_tovisit(user:user_dependency,db: db_dependency,tovisit_id: int=Path(gt=0)):
    if user is None :
        raise HTTPException(status_code=401, detail="Authentication Failed")

    tovisit = db.query(dbmodels.Tovisit).filter(dbmodels.Tovisit.id == tovisit_id)\
        .filter(dbmodels.Tovisit.user_id == user.get('user_id')).first()
    if tovisit is None:
        raise HTTPException(status_code=404, detail="Tovisit not found")
    return tovisit

@router.post("/tovisits/create", response_model=TovisitCreate, status_code=status.HTTP_201_CREATED)
async def create_tovisit(user:user_dependency,db: db_dependency, tovisit: TovisitCreate):
    if user is None :
        raise HTTPException(status_code=401, detail="Authentication Failed")
    db_tovisit = dbmodels.Tovisit(**tovisit.dict(),user_id=user.get('user_id'))
    db.add(db_tovisit)
    db.commit()
    db.refresh(db_tovisit)
    return db_tovisit

@router.put("/tovisits/update/{tovisit_id}", response_model=TovisitCreate, status_code=status.HTTP_200_OK)
async def update_tovisit(user:user_dependency,db: db_dependency, tovisit_id: int, tovisit: TovisitCreate):
    if user is None :
        raise HTTPException(status_code=401, detail="Authentication Failed")
    
    db_tovisit = db.query(dbmodels.Tovisit).filter(dbmodels.Tovisit.id == tovisit_id)\
        .filter(dbmodels.Tovisit.user_id == user.get('user_id')).first()
    if db_tovisit is None:
        raise HTTPException(status_code=404, detail="Tovisit not found")
    for key, value in tovisit.dict().items():
        setattr(db_tovisit, key, value)
    db.commit()
    db.refresh(db_tovisit)
    return db_tovisit

@router.delete("/tovisits/delete/{tovisit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tovisit(user:user_dependency,db: db_dependency, tovisit_id: int):
    if user is None :
        raise HTTPException(status_code=401, detail="Authentication Failed")
  
    db_tovisit = db.query(dbmodels.Tovisit).filter(dbmodels.Tovisit.id == tovisit_id)\
        .filter(dbmodels.Tovisit.user_id == user.get('user_id')).first()
    if db_tovisit is None:
        raise HTTPException(status_code=404, detail="Tovisit not found")
    db.delete(db_tovisit)
    db.commit()
    return None