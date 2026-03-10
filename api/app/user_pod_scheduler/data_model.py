"""用户 Pod 调度器数据模型"""

from typing import Optional
from pydantic import BaseModel, Field
from uuid import UUID


class CreatePodRequest(BaseModel):
    """创建 Pod 请求"""
    user_id: UUID = Field(..., description="用户ID")


class CreatePodResponse(BaseModel):
    """创建 Pod 响应"""
    success: bool = Field(..., description="操作是否成功")
    message: str = Field(..., description="操作结果消息")
    pod_name: Optional[str] = Field(None, description="Pod 名称")
    status: Optional[str] = Field(None, description="Pod 状态")
    is_new: Optional[bool] = Field(None, description="是否是新创建的")


class PodStatusResponse(BaseModel):
    """Pod 状态响应"""
    user_id: str = Field(..., description="用户ID")
    database_record: dict = Field(..., description="数据库记录")
    k8s_status: dict = Field(..., description="K8S 状态")
    lifetime_seconds: Optional[float] = Field(None, description="生存时间（秒）")
    juicefs_mount_path: Optional[str] = Field(None, description="JuiceFS 挂载路径")


class HeartbeatRequest(BaseModel):
    """心跳请求"""
    user_id: UUID = Field(..., description="用户ID")


class HeartbeatResponse(BaseModel):
    """心跳响应"""
    success: bool = Field(..., description="操作是否成功")
    message: str = Field(..., description="操作结果消息")


class UnloadPodResponse(BaseModel):
    """卸载 Pod 响应"""
    success: bool = Field(..., description="操作是否成功")
    message: str = Field(..., description="操作结果消息")