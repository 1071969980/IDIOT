import asyncio
from traceback import format_exception
from uuid import uuid4

import logfire
from loguru import logger
from sqlalchemy import Update
from sqlalchemy.orm import Session

from api.app.data_model import TaskStatus
from api.app.sql_orm import SuggestionMergeTask
from api.sql_orm_models.constant import SQL_ENGINE
from api.logger import log_span
from api.workflow.suggestion_merge_workflow import suggestion_merge_workflow

from .data_model import ReviewRisk, SuggestionMergeRequest, SuggestionMergeResponse


@log_span(message="suggestion_merge_task",
          args_captured_as_tags=["task_id"])
async def suggestion_merge_task(task_id: uuid4, request: SuggestionMergeRequest) -> None:
    # 设置数据库任务记录状态为running
    with Session(bind=SQL_ENGINE) as session:
        u = Update(SuggestionMergeTask)\
            .where(SuggestionMergeTask.uuid == str(task_id))\
            .values(stauts=TaskStatus.running)
        session.execute(u)
        session.commit()

    successed_flag = False
    fail_resones = ""
    try :
        # await asyncio.sleep(10)
        
        # 执行任务
        _res = await suggestion_merge_workflow(task_id, request.risks)

        successed_flag = True
    except Exception as e:
        logfire.error(str(e), details="\n".join(format_exception(e)))
        # 标记任务失败原因到数据库
        fail_resones = str(e)
    finally:
        pass
    
    # 设置数据库任务记录状态为success, 并保存结果
    if successed_flag:
        with Session(bind=SQL_ENGINE) as session:
            respones = SuggestionMergeResponse(
                stauts=TaskStatus.success,
                task_id=str(task_id),
                result=[_res],
            )
            u = Update(SuggestionMergeTask)\
                .where(SuggestionMergeTask.uuid == str(task_id))\
                .values(stauts=TaskStatus.success,
                        result=respones.model_dump_json())
            session.execute(u)
            session.commit()
    else:
        with Session(bind=SQL_ENGINE) as session:
            u = Update(SuggestionMergeTask)\
                .where(SuggestionMergeTask.uuid == str(task_id))\
                .values(stauts=TaskStatus.failed,
                        result=fail_resones)
            session.execute(u)
            session.commit()

async def _suggestion_merge(task_id: uuid4,
                           request: SuggestionMergeRequest) -> ReviewRisk:
    return await suggestion_merge_workflow(task_id, request.risks)