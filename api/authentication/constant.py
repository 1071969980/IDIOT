from fastapi import HTTPException, status
from .user_db_base import UserDBBase
from os import getenv

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

USER_DB : UserDBBase | None = None
if USER_DB is None:
    raise ValueError("USER_DB is not set")

JWT_SECRET_KEY = getenv("JWT_SECRET_KEY")
if JWT_SECRET_KEY is None:
    raise ValueError("JWT_SECRET_KEY is not set")