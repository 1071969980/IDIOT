from uuid import uuid4

import logfire
from loguru import logger
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.shared_params import ResponseFormatJSONObject

from api.app.contract_review.data_model import ReviewRisk
from api.app.logger import log_span
from api.llm.data_model import RetryConfig, RetryConfigForAPIError
from api.llm.generator import openai_async_generate
from api.llm.qwen import async_client as qwen_async_client

from .message_template import JINJA_ENV, AvailableTemplates


@log_span(message="suggestion_merge_workflow")
async def suggestion_merge_workflow(
    task_id: uuid4, risks: list[ReviewRisk]
) -> ReviewRisk:
    # merge risks
    with logfire.span(f"Suggestion Merge Workflow::merge_risks"):
        template = JINJA_ENV.get_template(AvailableTemplates.SuggestionMerge.value)
        user_prompt = template.render(risks=risks)

        logfire.info(
            f"Suggestion Merge Workflow::merge_risks::user_prompt: {user_prompt}"
        )

        qwen_client = qwen_async_client()
        model = "qwen3-235b-a22b"
        qwen_retry_config = RetryConfigForAPIError(
            situations={
                "limit_requests": RetryConfig(max_retry=10, retry_interval_seconds=10),
            },
        )

        messages = [ChatCompletionUserMessageParam(role="user", content=user_prompt)]

        streaming_response = await openai_async_generate(
            qwen_client,
            model=model,
            messages=messages,
            retry_configs=qwen_retry_config,
            stream=True,
            stream_options={"include_usage": True},
            extra_body={"enable_thinking": True},
        )

        if not streaming_response:
            logger.error(f"Suggestion Merge failed. Task ID: {task_id}")

        chunks_of_response = [chunk async for chunk in streaming_response]

        response_thinking_content = "".join(
            [
                chunk.choices[0].delta.model_extra.get("reasoning_content")
                if chunk.choices
                and chunk.choices[0].delta.model_extra.get("reasoning_content")
                else ""
                for chunk in chunks_of_response
            ]
        )
        response_content = "".join(
            [
                chunk.choices[0].delta.content
                if chunk.choices and chunk.choices[0].delta.content
                else ""
                for chunk in chunks_of_response
            ]
        )
        input_token_usage = chunks_of_response[-1].usage.prompt_tokens
        output_token_usage = chunks_of_response[-1].usage.completion_tokens
        token_usage = chunks_of_response[-1].usage.total_tokens

        logfire.info(
            "Suggestion Merge Workflow::merge_risks::response",
            thinking_content=response_thinking_content,
            content=response_content,
            input_token_usage=input_token_usage,
            output_token_usage=output_token_usage,
            token_usage=token_usage,
        )

    # format response content to json
    with logfire.span(f"Suggestion Merge Workflow::format_response"):
        template = JINJA_ENV.get_template(
            AvailableTemplates.SuggestionMergeJsonFormatter.value
        )
        system_prompt = template.render()
        messages = [
            ChatCompletionSystemMessageParam(role="system", content=system_prompt),
            ChatCompletionUserMessageParam(
                role="user",
                content=f"请帮我结构化如下的合并建议结果：\n\n{response_content}",
            ),
        ]

        response = await openai_async_generate(qwen_client,
                                    "qwen3-30b-a3b",
                                    messages,
                                    retry_configs=qwen_retry_config,
                                    response_format=ResponseFormatJSONObject(type="json_object"),
                                    extra_body={"enable_thinking": False},
                                    )
        
        response_content = response.choices[0].message.content
        input_token_usage = response.usage.prompt_tokens
        output_token_usage = response.usage.completion_tokens
        token_usage = response.usage.total_tokens

        logfire.info("Suggestion Merge Workflow::format result::response",
                     content=response_content,
                     input_token_usage=input_token_usage,
                     output_token_usage=output_token_usage,
                     token_usage=token_usage)
        
        return ReviewRisk.model_validate_json(response_content)
