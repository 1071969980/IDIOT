import datetime as dt
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from api.authentication import USER_DB
from api.core.env_config import auth_config

from .constant import CREDENTIALS_EXCEPTION, verify_password as verify_password_hash, AUTH_TOKEN_COOKIE_NAME
from .sql_stat.utils import _User

async def get_auth_header(request: Request) -> str | None:
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
    try :
        return await oauth2_scheme(request)
    except Exception:
        return None
def verify_password(plain_password: str, user: _User):
    """验证用户密码是否正确

    Args:
        plain_password: 原始密码
        user: 用户对象，包含hashed_password

    Returns:
        密码是否正确
    """
    return verify_password_hash(plain_password, user.hashed_password)


async def authenticate_user(username: str, password: str):
    user = await USER_DB.get_user_by_username(username)
    if not user:
        return False
    if not verify_password(password, user):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = dt.datetime.now(dt.UTC) + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, auth_config.jwt_secret_key.get_secret_value(), algorithm="HS256"), expire.timestamp()

async def get_current_user_from_token(token: str | None) -> _User:
    """从JWT token中获取当前用户"""
    if token is None or token == "null" or not token:
        raise CREDENTIALS_EXCEPTION
    try:
        payload = jwt.decode(token, auth_config.jwt_secret_key.get_secret_value(), algorithms="HS256")
        user_id: str = payload.get("sub")
        if user_id is None:
            raise CREDENTIALS_EXCEPTION
    except JWTError:
        raise CREDENTIALS_EXCEPTION
    user = await USER_DB.get_user_by_uuid(user_id)
    if user is None:
        raise CREDENTIALS_EXCEPTION
    return user


async def get_current_user(request: Request = None, token: str | None = Depends(get_auth_header)):
    """获取当前用户，优先从cookie验证，失败后回退到Bearer token"""
    # 先尝试从cookie获取remember_me token
    if request is not None:
        cookie_token = request.cookies.get(AUTH_TOKEN_COOKIE_NAME)
        if cookie_token:
            try:
                return await get_current_user_from_token(cookie_token)
            except HTTPException:
                # cookie验证失败，继续使用Bearer token
                pass

    # 使用Bearer token验证
    return await get_current_user_from_token(token)

async def get_current_active_user(
    request: Request = None, token: str | None = Depends(get_auth_header)
) -> _User:
    current_user = await get_current_user(request, token)
    if current_user.is_deleted:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_current_user_id(
    request: Request = None, token: str | None = Depends(get_auth_header)
) -> str:
    """获取当前用户ID，优先从cookie验证，失败后回退到Bearer token"""
    # 先尝试从cookie获取remember_me token
    if request is not None:
        cookie_token = request.cookies.get(AUTH_TOKEN_COOKIE_NAME)
        if cookie_token:
            try:
                payload = jwt.decode(cookie_token, auth_config.jwt_secret_key.get_secret_value(), algorithms="HS256")
                user_id: str = payload.get("sub")
                if user_id is not None:
                    return user_id
            except JWTError:
                # cookie验证失败，继续使用Bearer token
                pass

    # 使用Bearer token验证
    if token is None:
        raise CREDENTIALS_EXCEPTION
    try:
        payload = jwt.decode(token, auth_config.jwt_secret_key.get_secret_value(), algorithms="HS256")
        user_id: str = payload.get("sub")
        if user_id is None:
            raise CREDENTIALS_EXCEPTION
    except JWTError as e:
        raise CREDENTIALS_EXCEPTION from e
    return user_id