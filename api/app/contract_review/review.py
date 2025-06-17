from .router_declare import router
from .data_model import *

@router.post(
    "/review",
)
async def contract_review(request: ReviewRequest) -> ReviewResponse:
    pass


@router.get(
    "/review/{task_id}",
)
async def get_contract_review_result(task_id: str) -> ReviewResponse:
    pass