from fastapi import HTTPException, status

from os import getenv
from passlib.context import CryptContext


CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

JWT_SECRET_KEY = getenv("JWT_SECRET_KEY")
if JWT_SECRET_KEY is None:
    raise ValueError("JWT_SECRET_KEY is not set")

PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")