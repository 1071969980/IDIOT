from fastapi import APIRouter

router = APIRouter(
    prefix="/chunk",
    tags=["chunk"],
)