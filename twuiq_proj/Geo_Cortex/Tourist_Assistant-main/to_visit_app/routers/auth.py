from datetime import datetime, timedelta ,timezone
from re import U
from fastapi import APIRouter, Depends, HTTPException, status ,Request
from pydantic import BaseModel ,Field
from typing import Optional, List
from dbmodels import Users
from passlib.context import CryptContext
from typing import Annotated
from database import engin, SessionLocal
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from fastapi.templating import Jinja2Templates


router = APIRouter(prefix="/auth", tags=["auth"])

#configuration
##JWT configuration
SECRET_KEY = "9d872275fa78615bbd39f334c09ad2a0a1b122e5f259f2ae025bf4067f695330a2" #we can use openssl rand -r -hex 32 to generate a random key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


#//Variable for db connection and more /////////////////////////


# OAuth2PasswordBearer is a class that is used to get the token from the request header
FormInput = Annotated[OAuth2PasswordRequestForm, Depends()]

bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")#just for hashing the password

oauth2_bearer = OAuth2PasswordBearer(tokenUrl="/auth/token")#this will get the token from the request header


#//Function //////////////////////////
##its a dependency function for db connection to the router 
def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()
##just for db connection
db_dependency =  Annotated[Session, Depends(get_db)] 

tempaltes = Jinja2Templates(directory=r"F:\AI_APPS\Tourist_Assistant\templates")

### Pages ###

@router.get("/login-page")
def render_login_page(request: Request):
    return tempaltes.TemplateResponse("login.html", {"request": request})



@router.get("/register-page")
def render_register_page(request: Request):
    return tempaltes.TemplateResponse("register.html", {"request": request})

### Endpoints ###


##this is the function that will authenticate the user
##this function will check if the user exists in the db and if the password is correct
def authanticate_user(db: Session, username: str, password: str):
    user = db.query(Users).filter(Users.user_name == username).first()#this will get the user from the db
    if not user or not bcrypt_context.verify(password, user.hashed_password):#this will check if the password is correct
        return False
    return user #if the password is correct it will return the True

## function to create the access token
def create_access_token(username: str,user_id:int , expires_delta: timedelta ):
    encode = {"sub": username, "id": user_id}
    expires = datetime.now(timezone.utc)+ expires_delta 
    encode.update({"exp": expires}) #this will add the expiration time to the token
    return jwt.encode(encode, SECRET_KEY, algorithm=ALGORITHM) #this will encode the token
    
async def get_current_user(token: Annotated[str, Depends(oauth2_bearer)]):
    try:
        payload= jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]) #this will decode the token
        username: str = payload.get("sub") #this will get the username from the token
        user_id: int = payload.get("id") #this will get the user_id from the token
        if username is None or user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials", headers={"WWW-Authenticate": "Bearer"})
        return {"username": username, "user_id": user_id} #this will return the username and user_id
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials", headers={"WWW-Authenticate": "Bearer"})


#async def get_user_from_cookie_token(token: str):
#    try:
#        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#        username: str = payload.get("sub")
#        user_id: int = payload.get("id")
#        if username is None or user_id is None:
#            return None
#        return {"username": username, "user_id": user_id}
#    except JWTError:
#        return None
   

#//Classes /////////////////////////////////////////
class CreateUserRequest(BaseModel): #this is the request model for creating a user
    user_name: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    first_name: str = Field(..., min_length=3, max_length=50)
    last_name: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)
    role: str = Field(..., min_length=3, max_length=50)
    is_active: bool = True

class UserResponse(BaseModel):
    id: int
    email: str
    user_name: str
    first_name: str
    last_name: str
    role: str
    is_active: bool

    class Config:
        orm_mode = True
        
class Token(BaseModel):
    access_token: str
    token_type: str

#//////////////this is the crud operation //////////////////////////////////////////////////////
## class UserResponse(BaseModel): #this is the response model for creating a user
@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(db: db_dependency, create_user_request: CreateUserRequest):
    create_user_model = Users(
        user_name=create_user_request.user_name,
        email=create_user_request.email,
        first_name=create_user_request.first_name,
        last_name=create_user_request.last_name,
        hashed_password=bcrypt_context.hash(create_user_request.password),
        role=create_user_request.role,
        is_active=True
    )
    
    #check if the user already exists in the db
    
    db.add(create_user_model)#this will add the user model to the db session
    try:
        db.commit()#this will commit the user model to the db
        db.refresh(create_user_model)  #this will refresh the user model with the new data from the db
    except Exception as e:
        db.rollback()#this will rollback the db session if there is an error
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return create_user_model  #this will return the user model with the new data from the db


@router.post("/token", response_model=Token, status_code=status.HTTP_200_OK)
async def login_for_access_token(db: db_dependency,form_data:FormInput ):
    user = authanticate_user(db, form_data.username, form_data.password)
    #this will authenticate the user
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password", headers={"WWW-Authenticate": "Bearer"})
    
    token = create_access_token(user.user_name, user.id, timedelta(minutes=20)) #this will create the access token
    return {"access_token": token, "token_type": "bearer"}
    
 