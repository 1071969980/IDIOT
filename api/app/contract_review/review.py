import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import Select
from sqlalchemy.orm import Session

from api.app.data_model import TaskStatus
from api.app.db_orm_models import ContractReviewTask, sqllite_engine

from .data_model import ReviewRequest, ReviewResponse
from .review_task import contract_review_task
from .router_declare import router

"""
review.py

此模块提供了合同审查相关的API接口。
包括创建审查任务和获取审查结果的功能。
"""


@router.post(
    "/review",
)
async def contract_review(request: ReviewRequest) -> ReviewResponse:
    """创建一个新的合同审查任务。

    参数:
        request (ReviewRequest): 包含待审查条目的请求对象。

    返回:
        ReviewResponse: 包含新任务ID和初始状态的响应对象。

    流程:
        1. 创建数据库会话并初始化新任务记录。
        2. 提交任务至后台处理。
        3. 返回任务相关信息。
    """
    # 创建数据库会话
    session = Session(bind=sqllite_engine)
    try:
        # 创建新任务记录
        task_id = uuid4()
        new_task = ContractReviewTask(
            uuid=str(task_id),
            stauts=TaskStatus.init,  # 初始化任务状态
            create_time=datetime.now(tz=timezone(timedelta(hours=8))),
            result=None,       # 初始结果为空
        )
        session.add(new_task)
        session.commit()
        
        # 创建新任务
        loop = asyncio.get_event_loop()
        loop.create_task(contract_review_task(task_id, request))
        
        return ReviewResponse(
            stauts=TaskStatus.init,
            task_id=str(task_id),
            result=None,
        )
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


@router.get(
    "/review/{task_id}",
)
async def get_contract_review_result(task_id: str) -> ReviewResponse:
    """
    获取指定任务ID的合同审查结果。

    参数:
        task_id (str): 审查任务的唯一标识符。

    返回:
        ReviewResponse: 包含审查结果的任务信息。

    异常:
        HTTPException: 如果任务ID不存在，则返回404错误。
    """
    with Session(bind=sqllite_engine) as session:
        q = Select(ContractReviewTask)\
            .where(ContractReviewTask.uuid == task_id)
        q_res:ContractReviewTask = session.execute(q).one_or_none()
    
    if not q_res:
        raise HTTPException(
            status_code=404,
            detail="task_id not found",
        )
    task_status = TaskStatus(q_res.ContractReviewTask.stauts)
    task_res = q_res.ContractReviewTask.result
    if task_status == TaskStatus.success:
        return ReviewResponse.model_validate_json(task_res)
    elif task_status == TaskStatus.failed:
        return ReviewResponse(
            result=task_res,
            stauts=task_status,
            task_id=task_id,
        )
    else:
        return ReviewResponse(
            result=None,
            stauts=task_status,
            task_id=task_id,
        )