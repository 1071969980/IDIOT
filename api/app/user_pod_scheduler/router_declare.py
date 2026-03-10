from fastapi import APIRouter

router = APIRouter(
    prefix="/user-pod",
    tags=["User Pod Scheduler"],
)