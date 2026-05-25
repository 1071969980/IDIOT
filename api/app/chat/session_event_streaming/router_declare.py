from fastapi import APIRouter

router = APIRouter(
    prefix="/session_events",
    tags=["session_event_streaming"],
)
