import json

from pydantic import BaseModel, field_validator

from api.human_in_loop.interrupt import HILInterruptContent


class U2ASessionLinkData(BaseModel):
    title: str
    session_id: str

class A2ASessionLinkData(BaseModel):
    goal: str
    session_id: str

class ToolTaskResult(BaseModel):
    str_content: str
    json_content: dict | None = None
    occur_error: bool = False
    HIL_data: list[HILInterruptContent] | None = None
    u2a_session_link_data: U2ASessionLinkData | None = None
    a2a_session_link_data: A2ASessionLinkData | None = None

    @field_validator("json_content")
    @classmethod
    def validate_json_content_serializable(cls, v):
        """
        验证detail字段是否可以序列化为JSON
        支持原生Python字典或可以转为纯JSON的Pydantic BaseModel
        """
        # 如果是Pydantic BaseModel，检查其是否可以序列化为JSON
        if isinstance(v, BaseModel):
            try:
                # 尝试转换为dict，这会触发Pydantic的序列化验证
                v = v.model_dump(mode="json")
                return v
            except Exception as e:
                raise ValueError(f"json_content字段中的Pydantic模型无法序列化为JSON: {e}")

        # 如果是原生Python类型，尝试JSON序列化
        try:
            json.dumps(v)
            return v
        except (TypeError, ValueError) as e:
            raise ValueError(f"json_content字段无法序列化为JSON: {e}")

        # 其他情况都拒绝
        raise ValueError(f"detail字段必须是可JSON序列化的原生Python类型或Pydantic BaseModel，当前类型: {type(v)}")
