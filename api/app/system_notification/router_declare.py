from fastapi import APIRouter

router = APIRouter(
    prefix="/notifications",
    tags=["app-notification"],
)
