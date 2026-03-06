from pydantic import BaseModel, Field
from uuid import UUID


class CreateJuiceFSRequest(BaseModel):
    """创建 JuiceFS 资源的请求模型"""

    user_id: UUID = Field(..., description="用户ID")


class CreateJuiceFSResponse(BaseModel):
    """创建 JuiceFS 资源的响应模型"""

    success: bool = Field(..., description="操作是否成功")
    message: str = Field(..., description="操作结果消息")