import asyncio
from uuid import uuid4

from sqlalchemy import Select, Update
from sqlalchemy.orm import Session

from api.app.data_model import TaskStatus
from api.app.db_orm_models import SuggestionMergeTask, sqllite_engine

from .data_model import SuggestionMergeRequest, SuggestionMergeResponse, ReviewRisk

async def contract_review_task(task_id: uuid4, request: SuggestionMergeRequest) -> None:
    # 设置数据库任务记录状态为running
    with Session(bind=sqllite_engine) as session:
        u = Update(SuggestionMergeTask)\
            .where(SuggestionMergeTask.uuid == str(task_id))\
            .values(stauts=TaskStatus.running)
        session.execute(u)
        session.commit()

    successed_flag = False
    fail_resones = ""
    try :
        await asyncio.sleep(10)
        
        # mock 任务处理结果
        _res = [
            ReviewRisk(raw_text=risk.raw_text,
                        why_risk=risk.why_risk,
                        suggestion="merged suggestion")
            for risk in request.risks
        ]
        successed_flag = True
    except Exception as e:
        # TODO 记录日志
        # 标记任务失败原因到数据库
        pass
    finally:
        pass
    
    # 设置数据库任务记录状态为success, 并保存结果
    if successed_flag:
        with Session(bind=sqllite_engine) as session:
            respones = SuggestionMergeResponse(
                stauts=TaskStatus.success,
                task_id=str(task_id),
                result=_res,
            )
            u = Update(SuggestionMergeResponse)\
                .where(SuggestionMergeResponse.uuid == str(task_id))\
                .values(stauts=TaskStatus.success,
                        result=respones.model_dump_json())
            session.execute(u)
            session.commit()
    else:
        with Session(bind=sqllite_engine) as session:
            u = Update(SuggestionMergeResponse)\
                .where(SuggestionMergeResponse.uuid == str(task_id))\
                .values(stauts=TaskStatus.failed,
                        result=fail_resones)
            session.execute(u)
            session.commit()
