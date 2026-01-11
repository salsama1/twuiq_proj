from fastapi import APIRouter , Request ,Form
from models.schemas import QueryRequest, QueryResponse
from services.router_service import handle_query_with_contex ,handle_chat
from fastapi.templating import Jinja2Templates

query_router = APIRouter()


templates = Jinja2Templates(directory=r"F:\AI_APPS\Tourist_Assistant\templates")

@query_router.get("/chat")
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})




@query_router.post("/chat-query-form")
async def chat_query_form(request: Request, query: str = Form(...)):
    response_str = handle_query_with_contex(query)  # This returns a string
    return templates.TemplateResponse("chat.html", {
        "request": request,
        "query": query,
        "response": response_str
    })
    
    
@query_router.post("/query", response_model=QueryResponse)
async def query_llm(request: QueryRequest):
    response = handle_query_with_contex(request.query)
    return QueryResponse(response=response)
