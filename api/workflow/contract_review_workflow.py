from uuid import uuid4

import logfire
from loguru import logger
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.shared_params import ResponseFormatJSONObject
from pydantic import BaseModel

from api.app.contract_review.data_model import (
    ReviewEntry,
    ReviewResult,
    ReviewRisk,
    ReviewWorkflowResult,
)
from api.app.logger import log_span
from api.llm.data_model import RetryConfig, RetryConfigForAPIError
from api.llm.generator import openai_async_generate
from api.llm.qwen import async_client as qwen_async_client

from .message_template import JINJA_ENV, AvailableTemplates


class ReviewWorkflowResultForSingleEntry(BaseModel):
    entry: str
    entry_id: int
    risks: list[ReviewRisk]

class ReviewWorkflowResultUnaligned(BaseModel):
    result: list[ReviewWorkflowResultForSingleEntry]

@log_span(message="Contract Review Workflow")
async def contract_review_workflow(task_id: uuid4,
                                   contract_content_dict: dict[str, str],
                                   review_entrys: list[ReviewEntry],
                                   stance: str) -> ReviewWorkflowResult:
    with logfire.span(f"Contract Review Workflow::review_entrys"):
        # load template
        template = JINJA_ENV.get_template(AvailableTemplates.ContractReview.value)
        # render template
        review_entrys = [review_entry.model_dump() for review_entry in review_entrys]
        user_prompt = template.render(review_entrys=review_entrys,
                                        stance=stance,
                                        **contract_content_dict)
        messages = [
            ChatCompletionSystemMessageParam(role="system", content="你是一个助手，请按照用户要求完成合同审查。"),
            ChatCompletionUserMessageParam(role="user", content=user_prompt)
        ]

        logfire.info("Contract Review Workflow::review entrys::user prompt",
                     user_prompt=user_prompt)

        qwen_client = qwen_async_client()
        model = "deepseek-r1-0528"
        qwen_retry_config = RetryConfigForAPIError(
            error_code_to_match=[
                "limit_requests",
                "insufficient_quota",
            ]
        )

        streaming_response = await openai_async_generate(qwen_client,
                                                        model=model,
                                                        messages=messages,
                                                        retry_configs=qwen_retry_config,
                                                        stream=True,
                                                        stream_options={"include_usage": True})

        if not streaming_response:
            logfire.error(f"Contract review failed. Task ID: {task_id}")

        chunks_of_response = [chunk async for chunk in streaming_response]

        contract_review_response_thinking = "".join([chunk.choices[0].delta.model_extra.get("reasoning_content") \
                                                    if chunk.choices and \
                                                    chunk.choices[0].delta.model_extra.get("reasoning_content") \
                                                    else "" \
                                                    for chunk in chunks_of_response])
        contract_review_response = "".join([chunk.choices[0].delta.content \
                                            if chunk.choices and chunk.choices[0].delta.content \
                                            else "" \
                                            for chunk in chunks_of_response])
        input_token_usage = chunks_of_response[-1].usage.prompt_tokens
        output_token_usage = chunks_of_response[-1].usage.completion_tokens
        token_usage = chunks_of_response[-1].usage.total_tokens

        logfire.info("Contract Review Workflow::review entrys::response",
                     thinking_content=contract_review_response_thinking,
                     content=contract_review_response,
                     input_token_usage=input_token_usage,
                     output_token_usage=output_token_usage,
                     token_usage=token_usage)

    # call qwen to struct the contract review risk result
    with logfire.span(f"Contract Review Workflow::format result"):
        template = JINJA_ENV.get_template(AvailableTemplates.ContractReviewJsonFormatter.value)
        system_prompt = template.render()
        messages = [
            ChatCompletionSystemMessageParam(role="system", content=system_prompt),
            ChatCompletionUserMessageParam(role="user", content=f"请帮我结构化如下的合同审查结果：\n\n{contract_review_response}")
        ]

        response = await openai_async_generate(qwen_client,
                                            "qwen-plus",
                                            messages,
                                            retry_configs=qwen_retry_config,
                                            response_format=ResponseFormatJSONObject(type="json_object"),
                                            extra_body={"enable_thinking": False},
                                            )
        
        input_token_usage = response.usage.prompt_tokens
        output_token_usage = response.usage.completion_tokens
        token_usage = response.usage.total_tokens
        
        logfire.info("Contract Review Workflow::format result::response",
                     content=response.choices[0].message.content,
                     input_token_usage=input_token_usage,
                     output_token_usage=output_token_usage,
                     token_usage=token_usage)
    
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

    
