from fastapi import HTTPException, status

from os import getenv
from passlib.context import CryptContext
from fastapi.security import HTTPBearer
import secrets
import os



CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

JWT_SECRET_KEY = getenv("JWT_SECRET_KEY")
if JWT_SECRET_KEY is None:
    raise ValueError("JWT_SECRET_KEY is not set")

PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")

AUTH_HEADER = HTTPBearer()


def generate_salt(length: int = 32) -> str:
    """生成随机盐值

    Args:
        length: 盐值长度，默认32字节

    Returns:
        十六进制编码的盐值字符串
    """
    return secrets.token_hex(length)


def hash_password_with_salt(password: str, salt: str) -> str:
    """使用盐值对密码进行哈希

    Args:
        password: 原始密码
        salt: 盐值

    Returns:
        哈希后的密码
    """
    salted_password = password + salt
    return PWD_CONTEXT.hash(salted_password)


def verify_password_with_salt(password: str, salt: str, hashed_password: str) -> bool:
    """验证密码是否正确

    Args:
        password: 原始密码
        salt: 盐值
        hashed_password: 哈希后的密码

    Returns:
        密码是否正确
    """
    salted_password = password + salt
    return PWD_CONTEXT.verify(salted_password, hashed_password)