import asyncio
from uuid import uuid4

from sqlalchemy import Update
from sqlalchemy.orm import Session

from api.app.data_model import TaskStatus
from api.app.db_orm_models import ContractReviewTask, sqllite_engine

from .data_model import ReviewRequest, ReviewResult, ReviewResponse, ReviewRisk, ReviewStance, ReviewWorkflowResult

from traceback import format_exception
from loguru import logger

from api.workflow.contract_review_workflow import contract_review_workflow

async def contract_review_task(task_id: uuid4, request: ReviewRequest) -> None:
    # 设置数据库任务记录状态为running
    if request.delay > 0:
        await asyncio.sleep(request.delay)

    with Session(bind=sqllite_engine) as session:
        u = Update(ContractReviewTask)\
            .where(ContractReviewTask.uuid == str(task_id))\
            .values(stauts=TaskStatus.running)
        session.execute(u)
        session.commit()

    successed_flag = False
    fail_resones = ""
    try :
        workflow_res = await _contract_review(task_id=task_id, request=request)
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
                result=workflow_res.result,
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


async def _contract_review(task_id: uuid4,
                           request: ReviewRequest) -> ReviewWorkflowResult:
    stance = "中立"
    if request.stance == ReviewStance.PartyA:
        stance = "甲方"
    elif request.stance == ReviewStance.PartyB:
        stance = "乙方"

    tasks_for_chunks: list[asyncio.Task] = []

    for i, chunk in enumerate(request.chunks):
        # 获取当前审查的段落和相关上下文。目前是是滚动窗口方式
        contract_seg = chunk.parent
        contract_seg_pre_start_index = max(0, i - request.chunks_overlap)
        contract_seg_pre_end_index = i
        contract_seg_suf_start_index = min(len(request.chunks) - 1, i + 1)
        contract_seg_suf_end_index = min(len(request.chunks), i + request.chunks_overlap + 1)
        contract_seg_pre = "".join([_chunk.parent \
                                    for _chunk \
                                    in request.chunks[contract_seg_pre_start_index:contract_seg_pre_end_index]])
        contract_seg_suf = "".join([_chunk.parent \
                                   for _chunk \
                                   in request.chunks[contract_seg_suf_start_index:contract_seg_suf_end_index]])
        contract_content_dict = {
            "contract_seg": contract_seg,
            "contract_seg_pre": contract_seg_pre,
            "contract_seg_suf": contract_seg_suf,
        }

        tasks_for_chunks.append(
                asyncio.create_task(contract_review_workflow(task_id=task_id,
                                                            contract_content_dict=contract_content_dict,
                                                            review_entrys=request.entries,
                                                            stance=stance)))

    await asyncio.gather(*tasks_for_chunks)

    # 从 task 中获取结果
    tasks_for_chunks_results: list[ReviewWorkflowResult] = [task.result() for task in tasks_for_chunks]

    merged_result = ReviewWorkflowResult(result=[
        ReviewResult(
            entry=entry,
            risks=[],
        ) for entry in request.entries
    ])

    for result in tasks_for_chunks_results:
        _merge_into_single_result(merged_result, result)

    return merged_result

def _merge_into_single_result(merged_result: ReviewWorkflowResult,
                            _other: ReviewWorkflowResult) -> None:
    exist_entrys = [_res.entry for _res in merged_result.result]
    for _res in _other.result:
        if len(_res.risks) == 0:
            continue
        if _res.entry not in exist_entrys:
            merged_result.result.append(
                ReviewResult(
                    entry=_res.entry,
                    risks=_res.risks,
                ),
            )
        else:
            merged_result.result[exist_entrys.index(_res.entry)].risks.extend(
                _res.risks,
            )
