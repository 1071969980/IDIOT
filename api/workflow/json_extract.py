import json
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from openai.types.chat import (
    ChatCompletionUserMessageParam
)

from api.graph_executor import Graph
from api.graph_executor.graph_core import BypassSignal
from api.workflow.message_template import JINJA_ENV, AvailableTemplates
from api.load_balance.delegate.openai import generation_delegate_for_async_openai
from api.llm.generator import DEFAULT_RETRY_CONFIG
from api.load_balance import LOAD_BLANCER


def resolve_refs_and_remove_defs(schema: dict[str, Any]) -> dict[str, Any]:
    """
    解析JSON Schema中的$ref引用，将其替换为对应的定义，并删除$defs部分
    
    Args:
        schema: 包含$defs和$ref引用的JSON Schema字典
        
    Returns:
        处理后的JSON Schema字典，所有$ref已被替换，$defs已被删除
    """
    def _resolve_refs(obj: Any, defs: dict[str, Any]) -> Any:
        """递归解析对象中的$ref引用"""
        if isinstance(obj, dict):
            # 如果对象包含$ref，则替换为对应的定义
            if "$ref" in obj:
                ref_path = obj["$ref"]
                if ref_path.startswith("#/$defs/"):
                    def_name = ref_path.split("/")[-1]
                    if def_name in defs:
                        return _resolve_refs(defs[def_name], defs)
                    else:
                        raise ValueError(f"Definition '{def_name}' not found in $defs")
            
            # 递归处理字典中的所有值
            result = {}
            for key, value in obj.items():
                result[key] = _resolve_refs(value, defs)
            return result
        
        elif isinstance(obj, list):
            # 递归处理列表中的所有元素
            return [_resolve_refs(item, defs) for item in obj]
        
        else:
            # 基本类型直接返回
            return obj
    
    # 复制schema以避免修改原始数据
    schema_copy = schema.copy()
    
    # 获取definitions
    defs = schema_copy.get("$defs", {})
    
    # 解析所有引用
    resolved_schema = _resolve_refs(schema_copy, defs)
    
    # 删除$defs部分
    if "$defs" in resolved_schema:
        del resolved_schema["$defs"]
    
    return resolved_schema


@Graph("json_extract")
@dataclass
class TryExtractJsonFromDoc:
    llm_service_name: str
    doc: str
    json_schema: type[BaseModel]
    last_response: str|None = None
    error: str|None = None
    additional_msg: str|None = None

    async def run(self) -> tuple["EndNode", "ErrorNode"]:
        # 解析JSON Schema
        json_schema_dict = self.json_schema.model_json_schema()
        json_schema_dict = resolve_refs_and_remove_defs(json_schema_dict)
        json_schema_str = json.dumps(json_schema_dict, indent=2, ensure_ascii=False)
        # 构造用户提示
        template = JINJA_ENV.get_template(AvailableTemplates.JsonExtract)
        user_prompt = template.render(
            doc=self.doc,
            json_schema=json_schema_str,
            last_response=self.last_response,
            error=self.error,
            additional_msg=self.additional_msg,
        )
        message = [
            ChatCompletionUserMessageParam(content=user_prompt, role="user")
        ]
        # 调用LLM
        async def delegate(service_instance):
            return await generation_delegate_for_async_openai(
                service_instance,
                message,
                DEFAULT_RETRY_CONFIG
            )
        
        response = await LOAD_BLANCER.execute(
            self.llm_service_name,
            delegate,
        )

        response_content = response.choices[0].message.content

        try:
            pd_model = self.json_schema.model_validate_json(response_content)
            return EndNode(pd_model), BypassSignal(ErrorNode)
        
        except ValidationError as e:
            return BypassSignal(EndNode), ErrorNode(str(e), response_content, json_schema_str, self.llm_service_name)


@Graph("json_extract")
@dataclass
class EndNode:
    result: Any
    
    async def run(self) -> None:
        pass


@Graph("json_extract")
@dataclass
class ErrorNode:
    error: str
    last_response: str
    json_schema_str: str
    llm_service_name: str
    
    async def run(self) -> None:
        # 使用LLM解释ValidationError为更清晰的自然语言
        error_template = JINJA_ENV.get_template(AvailableTemplates.ErrorExplanation)
        error_prompt = error_template.render(
            validation_error=self.error,
            json_schema=self.json_schema_str
        )
        error_message = [
            ChatCompletionUserMessageParam(content=error_prompt, role="user")
        ]
        
        async def error_delegate(service_instance):
            return await generation_delegate_for_async_openai(
                service_instance,
                error_message,
                DEFAULT_RETRY_CONFIG
            )
        
        error_response = await LOAD_BLANCER.execute(
            self.llm_service_name,
            error_delegate,
        )
        
        self.error = error_response.choices[0].message.content

class FailedToExtractJsonError(Exception):
    pass

DATA_MODEL = TypeVar("DATA_MODEL")

async def extract_json_with_retry(
    llm_service_name: str,
    doc: str,
    json_schema: DATA_MODEL,
    max_retries: int = 1,
    additional_msg: str | None = None
) -> DATA_MODEL:
    """
    执行JSON提取图，支持最大重试次数直到获得有意义的结果
    
    Args:
        llm_service_name: LLM服务名称
        doc: 要提取JSON的文档内容
        json_schema: 目标JSON的Pydantic模型类型
        max_retries: 最大重试次数
        additional_msg: 附加消息
        
    Returns:
        提取的Pydantic模型实例   
    """
    last_response = None
    error = None

    for attempt in range(max_retries + 1):
        initial_node = TryExtractJsonFromDoc(
            llm_service_name=llm_service_name,
            doc=doc,
            json_schema=json_schema,
            last_response=last_response,
            error=error,
            additional_msg=additional_msg,
        )
        
        nodes, params = await Graph.start("json_extract", initial_node)
        
        end_node: EndNode = nodes.get("EndNode")
        if end_node and end_node.result is not None:
            return end_node.result
        
        error_node: ErrorNode = nodes.get("ErrorNode")
        if error_node and attempt < max_retries:
            last_response = error_node.last_response
            error = error_node.error
            
            continue
        
        if error_node:
            raise FailedToExtractJsonError(error_node.error)
    
    raise FailedToExtractJsonError("Failed to extract JSON")

