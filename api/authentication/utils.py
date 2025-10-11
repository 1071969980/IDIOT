import datetime as dt
from datetime import timedelta

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from api.authentication import USER_DB

from .constant import CREDENTIALS_EXCEPTION, JWT_SECRET_KEY, verify_password_with_salt
from .sql_stat.utils import _User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
def verify_password(plain_password: str, user: _User):
    """验证用户密码是否正确

    Args:
        plain_password: 原始密码
        user: 用户对象，包含hashed_password和salt

    Returns:
        密码是否正确
    """
    return verify_password_with_salt(plain_password, user.salt, user.hashed_password)


async def authenticate_user(username: str, password: str):
    user = await USER_DB.get_user_by_username(username)
    if not user:
        return False
    if not verify_password(password, user):
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
        user_id: str = payload.get("sub")
        if user_id is None:
            raise CREDENTIALS_EXCEPTION
    except JWTError:
        raise CREDENTIALS_EXCEPTION
    user = await USER_DB.get_user_by_uuid(user_id)
    if user is None:
        raise CREDENTIALS_EXCEPTION
    return user

def get_current_active_user(current_user: _User = Depends(get_current_user)):
    if current_user.is_deleted:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def get_current_user_id(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms="HS256")
        user_id: str = payload.get("sub")
        if user_id is None:
            raise CREDENTIALS_EXCEPTION
    except JWTError:
        raise CREDENTIALS_EXCEPTION
    return user_id