import asyncio
import base64
import json
from io import BytesIO
from traceback import format_exception
from typing import Annotated, Any

import logfire
from fastapi import File, Form, HTTPException, UploadFile
from openai.types.chat import (
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionUserMessageParam,
)
from openai.types.shared_params import ResponseFormatJSONObject
from PIL import Image
from PIL.ImageFile import ImageFile

from api.app.logger import log_span
from api.llm.data_model import RetryConfigForAPIError
from api.load_balance import (
    LOAD_BLANCER,
    QWEN_3_235B_SERVICE_NAME,
    QWEN_VL_OCR_SERVICE_NAME,
)
from api.load_balance.delegate.openai import generation_delegate_for_async_openai

from .data_model import RecognizeRequest, RecognizeResponse
from .router_declare import router

"""_summary_
识别上传的图片，并转成对应的json schema描述

这部分接口将会是阻塞的
"""


@router.post("/recognize")
async def receipet_recognize(
    file: Annotated[
        UploadFile, File(description="通过表单上传的文件对象，需符合允许的扩展名格式。"),
    ],
    request_data:str = Form(...),
) -> RecognizeResponse:
    # 检查文件的后缀是否为常见的图片格式
    request_data = RecognizeRequest.model_validate_json(request_data)
    image_extensions = ["jpg", "jpeg", "png", "bmp"]
    file_extension = file.filename.lower().split(".")[-1]
    if not file_extension.endswith(tuple(image_extensions)):
        raise HTTPException(status_code=400, detail=f"Invalid file type {file_extension}")
    image = Image.open(file.file)

    try:
        # 将文件转成png格式,并转为base64
        image_base64 = image_to_base64(image)

        with logfire.span("receipet_recognize_task"):
            # 调用ocr服务将文件转为文本
            ocr_res = await receipet_ocr_by_qwen_vl_ocr(
                image_base64, "jpg", request_data.hot_words,
            )
            # 并发调用语言模型将ocr结果转为json格式数据
            json_results = await format_ocr_res_to_json(
                ocr_res, request_data.json_schemaes,
            )
            # 将json结果合并到一起
            json_res = merge_json_res(json_results)
            json_res = json.dumps(json_res, ensure_ascii=False)

            logfire.info("receipet_recognize_task::result",
                         json_res=json_res,
                         ocr_res=ocr_res,
                         )

            return RecognizeResponse(
                json_res=json_res,
                ocr_res=ocr_res,
            )

    except Exception as e:
        logfire.error(str(e), detail="\n".join(format_exception(e)))
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error, \n" + "\n".join(format_exception(e)),
        ) from e


def image_to_base64(image: ImageFile) -> str:
    """
    将图片转为base64
    """
    image_b = BytesIO()
    rgb = image.convert("RGB")
    rgb.save(image_b, format="jpeg")
    return base64.b64encode(image_b.getvalue()).decode()


@log_span(
    "receipet_recognize_task::vl_ocr",
)
async def receipet_ocr_by_qwen_vl_ocr(
    image_base64: str,
    image_type: str,
    hot_words: list[str] | None = None,
) -> str:
    """
    调用 ocr 服务进行图片识别
    """
    image_url = f"data:image/{image_type};base64,{image_base64}"

    user_prompt = """请帮我将这张图片转可线性阅读的文本，以markdown格式输出。输出表格时，在每一行加上行号。
    重点关注材料及其属性，公司或其他实体。尽可能完整的输出所有文字。
    请注意文档中的图表和复杂表格和信息之间的阅读关系。
    不要产生幻觉。不要省略信息。在生成结果时，请注意根据语义关系避免错别字。\n"""

    if hot_words:
        user_prompt += "以下是你需要注意的关键词(热词),用分号分隔,可以在图片模糊不清或文档表达不准确时参考:\n"
        for hot_word in hot_words:
            user_prompt += f"{hot_word};"
        user_prompt += "\n\n"

    messages = [
        ChatCompletionUserMessageParam(
            role="user",
            content=[ChatCompletionContentPartImageParam(type="image_url", image_url=image_url),
                     ChatCompletionContentPartTextParam(type="text", text=user_prompt)]
        ),
    ]

    qwen_retry_config = RetryConfigForAPIError(
        error_code_to_match=[
            "limit_requests",
            "insufficient_quota",
        ],
    )

    async def delegate(service_instance):
        return await generation_delegate_for_async_openai(
            service_instance,
            messages,
            qwen_retry_config,
        )

    response = await LOAD_BLANCER.execute(
        QWEN_VL_OCR_SERVICE_NAME,
        delegate,
    )

    input_token_usage = response.usage.prompt_tokens
    output_token_usage = response.usage.completion_tokens
    token_usage = response.usage.total_tokens

    logfire.info(
        "receipet_recognize_task::vl_ocr::response",
        content=response.choices[0].message.content,
        input_token_usage=input_token_usage,
        output_token_usage=output_token_usage,
        token_usage=token_usage,
    )

    return response.choices[0].message.content


@log_span("receipt_recognize_task::json_formatter")
async def format_ocr_res_to_json(
    content: str,
    json_schemaes: list[dict],
) -> list[dict]:
    tasks = [
        asyncio.create_task(
            json_format_task(
                content=content,
                json_schema=schema,
            ),
        )
        for schema in json_schemaes
    ]

    __tasks_results = await asyncio.gather(*tasks, return_exceptions=True)

    tasks_results_json = [
        result for result in __tasks_results if not isinstance(result, Exception)
    ]
    tasks_exceptions = [
        result for result in __tasks_results if isinstance(result, Exception)
    ]

    for e in tasks_exceptions:
        logfire.error(str(e), detail="\n".join(format_exception(e)))

    tasks_results_dict = []

    for result in tasks_results_json:
        try:
            tasks_results_dict.append(json.loads(result))
        except Exception as e:
            logfire.error(str(e), detail="\n".join(format_exception(e)))

    return tasks_results_dict


@log_span(
    "receipt_recognize_task::json_formatter::task",
    args_captured_as_tags=["content", "json_schema"],
)
async def json_format_task(content: str, json_schema: dict) -> str:
    user_propmt = """
    ---\n
    请帮我将如上的文档转化成json格式的数据，json的约束请见如下以JSON Schema标准的编写的描述\n
    ---\n
    """
    user_propmt = content + "\n" + user_propmt
    user_propmt = user_propmt + json.dumps(json_schema, indent=2, ensure_ascii=False)

    messages = [
        {"role": "user", "content": user_propmt},
    ]

    qwen_retry_config = RetryConfigForAPIError(
        error_code_to_match=[
            "limit_requests",
            "insufficient_quota",
        ],
    )

    async def delegate(service_instance):
        return await generation_delegate_for_async_openai(
            service_instance,
            messages,
            qwen_retry_config,
            response_format=ResponseFormatJSONObject(type="json_object"),
            extra_body={"enable_thinking": False},
        )

    response = await LOAD_BLANCER.execute(
        QWEN_3_235B_SERVICE_NAME,
        delegate,
    )

    response_content = response.choices[0].message.content

    input_token_usage = response.usage.prompt_tokens
    output_token_usage = response.usage.completion_tokens
    token_usage = response.usage.total_tokens

    logfire.info(
        "receipet_recognize_task::json_formatter::task::response",
        content=response.choices[0].message.content,
        input_token_usage=input_token_usage,
        output_token_usage=output_token_usage,
        token_usage=token_usage,
    )

    return response_content


@log_span("receipt_recognize_task::merge_json_res")
def merge_json_res(json_res: list[dict]) -> dict:
    final_res: dict = {}
    for d in json_res:
        for key, value in d.items():
            if key not in final_res:
                final_res[key] = value
            else:
                _merge_kv_to_exist(final_res, key, value)
    return final_res

def _merge_kv_to_exist(final_res: dict, key: str, value: Any):
    if isinstance(value, list):
        _merge_list_value_to_exist(final_res, key, value)
    elif isinstance(value, str):
        final_res[key] = value
    else:
        final_res[key] = value
    return final_res

def _merge_list_value_to_exist(final_res: dict, key: str, value: list):
    if not isinstance(final_res[key], list):
        final_res[key] = value
        return
    else:
        targer_list:list = final_res[key]
        for item in value:
            if not isinstance(item, dict):
                targer_list.append(item)
            else:
                major_key = list(item.keys())[0]
                major_value = item[major_key]
                for exist_item in targer_list:
                    if not isinstance(exist_item, dict):
                        continue
                    exist_major_value = exist_item.get(major_key, None)
                    if exist_major_value == major_value:
                        exist_item.update(item)
                        break