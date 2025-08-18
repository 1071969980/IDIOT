from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Depends, HTTPException
from api.authentication.utils import authenticate_user, create_access_token, get_current_active_user
from api.authentication.data_model import UserBase

from .router_declare import router

@router.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="认证失败")
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


async def example_auth_required_api(user: UserBase = Depends(get_current_active_user)):
    pass