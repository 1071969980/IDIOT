from .router_declare import router
from uuid import uuid4
from .data_model import SuggestionMergeRequest, SuggestionMergeResponse
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException
from sqlalchemy import Select
from api.app.data_model import TaskStatus
from api.app.db_orm_models import SuggestionMergeTask, sqllite_engine

import asyncio

@router.post(
    "/suggestion_merge",
)
async def suggestion_merge(request: SuggestionMergeRequest) -> SuggestionMergeResponse:
    # 创建数据库会话
    session = Session(bind=sqllite_engine)
    try:
        # 创建新任务记录
        task_id = uuid4()
        new_task = SuggestionMergeTask(
            uuid=str(task_id),
            stauts=TaskStatus.init,  # 初始化任务状态
            create_time=datetime.now(tz=timezone(timedelta(hours=8))),
            result=None,       # 初始结果为空
        )
        session.add(new_task)
        session.commit()
        
        # 创建新任务
        loop = asyncio.get_event_loop()
        # TODO
        
        return SuggestionMergeResponse(
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
    "/suggestion_merge/{task_id}",
)
async def get_suggestion_merge_result(task_id: str) -> SuggestionMergeResponse:
    with Session(bind=sqllite_engine) as session:
        q = Select(SuggestionMergeTask)\
            .where(SuggestionMergeTask.uuid == task_id)
        q_res = session.execute(q).one_or_none()
    
    if not q_res:
        raise HTTPException(
            status_code=404,
            detail="task_id not found",
        )
    task_status = TaskStatus(q_res.SuggestionMergeTask.stauts)
    task_res = q_res.SuggestionMergeTask.result
    if task_status == TaskStatus.success:
        return SuggestionMergeResponse.model_validate_json(task_res)
    elif task_status == TaskStatus.failed:
        return SuggestionMergeResponse(
            result=task_res,
            stauts=task_status,
            task_id=task_id,
        )
    else:
        return SuggestionMergeResponse(
            result=None,
            stauts=task_status,
            task_id=task_id,
        )
    