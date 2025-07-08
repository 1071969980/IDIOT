from fastapi import APIRouter

__all__ = ["router"]

router = APIRouter(
    prefix="/receipt_recognize",
    tags=["receipt_recognize"],
)