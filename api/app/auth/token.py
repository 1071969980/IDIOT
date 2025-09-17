from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Depends, HTTPException
from api.authentication.utils import authenticate_user, create_access_token, get_current_active_user
from api.authentication.data_model import UserBase
from api.authentication.constant import AUTH_HEADER
from api.authentication import USER_DB

from .router_declare import router

@router.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="认证失败")
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/signup")
async def signup(username:str, password:str):
    USER_DB.create_user(username=username, password=password)


@router.post("/token_healthy")
async def example_auth_required_api(auth_header: str = Depends(AUTH_HEADER), # decalre this for swagger UI generating a button to input the token
                                    user: UserBase = Depends(get_current_active_user)): # Using Depends validate the token and return the user
    pass