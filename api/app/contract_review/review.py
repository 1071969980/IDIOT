from .router_declare import router
from .data_model import *
from uuid import uuid4
from api.app.data_model import TaskStatus

@router.post(
    "/review",
)
async def contract_review(request: ReviewRequest) -> ReviewResponse:
    task_id = str(uuid4())
    
    # 动态生成审查结果，使用请求中的条目
    return ReviewResponse(
        stauts=TaskStatus.running,
        task_id=task_id,
        result=None
    )
    


@router.get(
    "/review/{task_id}",
)
async def get_contract_review_result(task_id: str) -> ReviewResponse:
    pass