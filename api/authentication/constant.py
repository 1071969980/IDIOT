from fastapi import HTTPException, status
from fastapi.responses import Response

import bcrypt
from fastapi.security import HTTPBearer

from api.core.env_config import auth_config


CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

# JWT 配置 (从 auth_config 获取)
JWT_SECRET_KEY = auth_config.jwt_secret_key.get_secret_value()

# Remember Me 功能配置 (从 auth_config 获取)
AUTH_TOKEN_COOKIE_NAME = auth_config.auth_token_cookie_name
REMEMBER_ME_EXPIRE_DAYS = auth_config.remember_me_expire_days
REMEMBER_ME_COOKIE_DOMAIN = auth_config.remember_me_cookie_domain
REMEMBER_ME_COOKIE_SECURE = auth_config.remember_me_cookie_secure
REMEMBER_ME_COOKIE_HTTPONLY = auth_config.remember_me_cookie_httponly
REMEMBER_ME_COOKIE_SAMESITE = auth_config.remember_me_cookie_samesite


def set_auth_token_cookie(response: Response, token: str, expire_time:int) -> Response:
    """设置 auth_token cookie

    Args:
        response: FastAPI Response 对象
        token: auth_token token
        expire_time: token 过期时间

    Returns:
        设置了cookie的Response对象
    """
    response.set_cookie(
        key=AUTH_TOKEN_COOKIE_NAME,
        value=token,
        max_age=expire_time,
        expires=expire_time,
        domain=REMEMBER_ME_COOKIE_DOMAIN,
        path="/",
        secure=REMEMBER_ME_COOKIE_SECURE,
        httponly=REMEMBER_ME_COOKIE_HTTPONLY,
    )
    return response

def set_remember_me_cookie(response: Response, token: str) -> Response:
    """设置 remember_me cookie

    Args:
        response: FastAPI Response 对象
        token: remember_me token

    Returns:
        设置了cookie的Response对象
    """
    return set_auth_token_cookie(response, token, REMEMBER_ME_EXPIRE_DAYS * 24 * 60 * 60)


def clear_auth_token_cookie(response: Response) -> Response:
    """清除 remember_me cookie

    Args:
        response: FastAPI Response 对象

    Returns:
        清除了cookie的Response对象
    """
    response.set_cookie(
        key=AUTH_TOKEN_COOKIE_NAME,
        value="",
        max_age=0,
        expires=0,
        domain=REMEMBER_ME_COOKIE_DOMAIN,
        secure=REMEMBER_ME_COOKIE_SECURE,
        httponly=REMEMBER_ME_COOKIE_HTTPONLY,
        samesite=REMEMBER_ME_COOKIE_SAMESITE,
    )
    return response


def hash_password(password: str) -> str:
    """对密码进行哈希

    Args:
        password: 原始密码

    Returns:
        哈希后的密码（bcrypt 格式，内含盐值）
    """
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed_password: str) -> bool:
    """验证密码是否正确

    Args:
        password: 原始密码
        hashed_password: 哈希后的密码

    Returns:
        密码是否正确
    """
    return bcrypt.checkpw(password.encode(), hashed_password.encode())