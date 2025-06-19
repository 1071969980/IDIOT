import asyncio
from uuid import uuid4

from sqlalchemy import Update
from sqlalchemy.orm import Session

from api.app.data_model import TaskStatus
from api.app.db_orm_models import ContractReviewTask, sqllite_engine

from .data_model import ReviewRequest, ReviewResult, ReviewResponse, ReviewRisk

from traceback import format_exception
from loguru import logger

async def contract_review_task(task_id: uuid4, request: ReviewRequest) -> None:
    # 设置数据库任务记录状态为running
    with Session(bind=sqllite_engine) as session:
        u = Update(ContractReviewTask)\
            .where(ContractReviewTask.uuid == str(task_id))\
            .values(stauts=TaskStatus.running)
        session.execute(u)
        session.commit()

    successed_flag = False
    fail_resones = ""
    try :
        await asyncio.sleep(10)
        
        # mock 任务处理结果
        _res = [
            ReviewResult(
                entry=entry,
                risks=[ReviewRisk(raw_text="Risk_1_brief",
                                why_risk="Potential issue in brief",
                                suggestion="Suggestion for Risk_1_brief")]
            )
            for entry in request.entries
        ]
        successed_flag = True
    except Exception as e:
        logger.error(str(e))
        logger.error(format_exception(e))
        # 标记任务失败原因到数据库
        fail_resones = str(e)
    finally:
        pass
    
    # 设置数据库任务记录状态为success, 并保存结果
    if successed_flag:
        with Session(bind=sqllite_engine) as session:
            respones = ReviewResponse(
                stauts=TaskStatus.success,
                task_id=str(task_id),
                result=_res,
            )
            u = Update(ContractReviewTask)\
                .where(ContractReviewTask.uuid == str(task_id))\
                .values(stauts=TaskStatus.success,
                        result=respones.model_dump_json())
            session.execute(u)
            session.commit()
    else:
        with Session(bind=sqllite_engine) as session:
            u = Update(ContractReviewTask)\
                .where(ContractReviewTask.uuid == str(task_id))\
                .values(stauts=TaskStatus.failed,
                        result=fail_resones)
            session.execute(u)
            session.commit()
