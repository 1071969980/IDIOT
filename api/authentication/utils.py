import datetime as dt
from datetime import timedelta

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from api.authentication import USER_DB

from .constant import CREDENTIALS_EXCEPTION, JWT_SECRET_KEY, PWD_CONTEXT
from .data_model import UserModel
from .user_db_base import UserDBBase


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
def verify_password(plain_password, hashed_password):
    return PWD_CONTEXT.verify(plain_password, hashed_password)


async def authenticate_user(username: str, password: str):
    user = await USER_DB.get_user_by_username(username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = dt.datetime.now(dt.UTC) + expires_delta
    else:
        expire = dt.datetime.now(dt.UTC) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm="HS256")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms="HS256")
        username: str = payload.get("sub")
        if username is None:
            raise CREDENTIALS_EXCEPTION
    except JWTError:
        raise CREDENTIALS_EXCEPTION
    user = await USER_DB.get_user_by_username(username)
    if user is None:
        raise CREDENTIALS_EXCEPTION
    return user

def get_current_active_user(current_user: UserModel = Depends(get_current_user)):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
