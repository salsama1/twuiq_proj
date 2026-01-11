from pydantic import BaseModel

#for new user query request and response schemas
from typing import List, Optional

class PlaceInfo(BaseModel):
    uuid: str
    poi_name: str
    lat: float
    lng: float
    reviews_no: Optional[float] = None
    price_range: Optional[str] = None
    category: Optional[str] = None



class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    response: str
    places: Optional[List[PlaceInfo]] = None