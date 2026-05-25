"""user_pod_scheduler 服务 HTTP 客户端"""

import httpx
import logfire
from uuid import UUID
from typing import Optional

from api.app.user_pod_scheduler.data_model import (
    CreatePodResponse,
    PodStatusResponse,
    HeartbeatResponse,
)
from api.logger.logger import log_span

from .constants import SCHEDULER_SERVICE_URL
from .exceptions import SchedulerServiceError


class SchedulerClient:
    """user_pod_scheduler 服务 HTTP 客户端"""

    def __init__(self, base_url: str = SCHEDULER_SERVICE_URL):
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @log_span("查询 Pod 状态", args_captured_as_tags=["user_id", "image"])
    async def get_pod_status(self, user_id: UUID, image: str | None = None) -> PodStatusResponse:
        """
        查询用户 Pod 状态

        Args:
            user_id: 用户ID
            image: 容器镜像

        Returns:
            PodStatusResponse: Pod 状态信息

        Raises:
            SchedulerServiceError: 服务调用失败
        """
        client = await self._get_client()
        url = f"{self.base_url}/user-pod/status/{user_id}"
        params = {}
        if image:
            params["image"] = image

        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return PodStatusResponse(**response.json())
        except httpx.HTTPStatusError as e:
            logfire.error(f"Failed to get pod status: {e}")
            raise SchedulerServiceError(f"Failed to get pod status: {e}")
        except httpx.RequestError as e:
            logfire.error(f"Request error: {e}")
            raise SchedulerServiceError(f"Request error: {e}")

    @log_span("创建 Pod", args_captured_as_tags=["user_id", "image"])
    async def create_pod(self, user_id: UUID, image: str | None = None) -> CreatePodResponse:
        """
        创建或拉起用户 Pod

        Args:
            user_id: 用户ID
            image: 容器镜像

        Returns:
            CreatePodResponse: 创建结果

        Raises:
            SchedulerServiceError: 服务调用失败
        """
        client = await self._get_client()
        url = f"{self.base_url}/user-pod/create"

        body: dict = {"user_id": str(user_id)}
        if image:
            body["image"] = image

        try:
            response = await client.post(url, json=body)
            response.raise_for_status()
            return CreatePodResponse(**response.json())
        except httpx.HTTPStatusError as e:
            logfire.error(f"Failed to create pod: {e}")
            raise SchedulerServiceError(f"Failed to create pod: {e}")
        except httpx.RequestError as e:
            logfire.error(f"Request error: {e}")
            raise SchedulerServiceError(f"Request error: {e}")

    @log_span("发送心跳", args_captured_as_tags=["user_id", "image"])
    async def send_heartbeat(self, user_id: UUID, image: str | None = None) -> HeartbeatResponse:
        """
        刷新用户 Pod 心跳

        Args:
            user_id: 用户ID
            image: 容器镜像

        Returns:
            HeartbeatResponse: 心跳响应

        Raises:
            SchedulerServiceError: 服务调用失败
        """
        client = await self._get_client()
        url = f"{self.base_url}/user-pod/heartbeat"

        body: dict = {"user_id": str(user_id)}
        if image:
            body["image"] = image

        try:
            response = await client.post(url, json=body)
            response.raise_for_status()
            return HeartbeatResponse(**response.json())
        except httpx.HTTPStatusError as e:
            logfire.warning(f"Failed to send heartbeat: {e}")
            return HeartbeatResponse(success=False, message=str(e))
        except httpx.RequestError as e:
            logfire.warning(f"Request error: {e}")
            return HeartbeatResponse(success=False, message=str(e))

    @log_span("卸载 Pod（仅 Pod）", args_captured_as_tags=["user_id", "image"])
    async def unload_pod_only(self, user_id: UUID, image: str | None = None) -> bool:
        """
        卸载用户 Pod（仅删除 Pod，保留 JuiceFS 资源）

        Args:
            user_id: 用户ID
            image: 容器镜像

        Returns:
            bool: 是否成功
        """
        client = await self._get_client()
        url = f"{self.base_url}/user-pod/unload/{user_id}"
        params = {}
        if image:
            params["image"] = image

        try:
            response = await client.delete(url, params=params)
            response.raise_for_status()
            return response.json().get("success", False)
        except httpx.HTTPStatusError as e:
            logfire.error(f"Failed to unload pod: {e}")
            return False
        except httpx.RequestError as e:
            logfire.error(f"Request error: {e}")
            return False


# 全局客户端实例
_scheduler_client: Optional[SchedulerClient] = None


def get_scheduler_client() -> SchedulerClient:
    """获取全局调度器客户端实例"""
    global _scheduler_client
    if _scheduler_client is None:
        _scheduler_client = SchedulerClient()
    return _scheduler_client
