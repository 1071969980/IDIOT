from uuid import uuid4

from loguru import logger
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from pydantic import BaseModel

from api.app.contract_review.data_model import (
    ReviewEntry,
    ReviewResult,
    ReviewRisk,
    ReviewWorkflowResult,
)
from api.llm.generator import openai_async_generate
from api.llm.qwen import async_client as qwen_async_client

from .message_template import JINJA_ENV, AvailableTemplates


class ReviewWorkflowResultForSingleEntry(BaseModel):
    entry: str
    entry_id: int
    risks: list[ReviewRisk]

class ReviewWorkflowResultUnaligned(BaseModel):
    result: list[ReviewWorkflowResultForSingleEntry]

async def contract_review_workflow(task_id: uuid4,
                                   context: str,
                                   review_entrys: list[ReviewEntry],
                                   stance: str) -> ReviewWorkflowResult:
    # call farui to complete the contract review

    # load template
    template = JINJA_ENV.get_template(AvailableTemplates.ContractReview.value)
    # render template
    review_entrys = [review_entry.model_dump() for review_entry in review_entrys]
    system_prompt = template.render(context=context,
                                    review_entrys=review_entrys,
                                    stance=stance)
    messages = [
        ChatCompletionSystemMessageParam(role="system", content=system_prompt),
        ChatCompletionUserMessageParam(role="user", content="请根据上述要求帮我完成合同审查。")
    ]

    qwen_client = qwen_async_client()

    response = await openai_async_generate(qwen_client,
                                            model="deepseek-r1-0528",
                                            messages=messages)

    if not response:
        logger.error(f"Contract review failed. Task ID: {task_id}")

    contract_review_response = response.choices[0].message.content

    # call qwen to struct the contract review risk result

    template = JINJA_ENV.get_template(AvailableTemplates.ContractReviewJsonFormatter.value)
    system_prompt = template.render()
    messages = [
        ChatCompletionSystemMessageParam(role="system", content=system_prompt),
        ChatCompletionUserMessageParam(role="user", content=f"请帮我结构化如下的合同审查结果：\n\n{contract_review_response}")
    ]

    from openai.types.shared_params import ResponseFormatJSONObject

    response = await openai_async_generate(qwen_client,
                                           "qwen3-30b-a3b",
                                           messages,
                                           response_format=ResponseFormatJSONObject(type="json_object"),
                                           extra_body={"enable_thinking": False},
                                           )
    
    # aligned response to entry

    workflow_res_unaligned = ReviewWorkflowResultUnaligned.model_validate_json(
        response.choices[0].message.content
    )

    workflow_res = ReviewWorkflowResult(result=[])

    for _res in workflow_res_unaligned.result:
        workflow_res.result.append(
            ReviewResult(
                entry=review_entrys[_res.entry_id - 1], # LLM count entry_id start from 1
                risks=_res.risks,
            ),
        )
    
    return workflow_res

    
