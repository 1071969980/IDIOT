import datetime as dt
from datetime import timedelta

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from .constant import CREDENTIALS_EXCEPTION, JWT_SECRET_KEY, USER_DB, USR_NAME_KEY
from .data_model import UserBase
from .user_db_base import UserDBBase

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def authenticate_user(user_db: UserDBBase, username: str, password: str):
    user = user_db.get_user(username)
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

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms="HS256")
        username: str = payload.get(USR_NAME_KEY)
        if username is None:
            raise CREDENTIALS_EXCEPTION
    except JWTError:
        raise CREDENTIALS_EXCEPTION
    user = USER_DB.get_user(username)
    if user is None:
        raise CREDENTIALS_EXCEPTION
    return user

def get_current_active_user(current_user: UserBase = Depends(get_current_user)):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
