"""IDIOT_RBAC 服务 HTTP 客户端

复用项目既有约定（``httpx.AsyncClient`` 懒加载单例、``@log_span`` 追踪），
对 IDIOT_RBAC 的鉴权与策略管理接口做原子方法封装。

服务地址与鉴权 token 由统一配置模块 ``api.core.env_config`` 提供。
IDIOT_RBAC 为 headless StatefulSet（``clusterIP: None``），客户端只需使用单个
base_url 访问服务 DNS，Pod 内部会按 owner 哈希透明转发到目标分片，调用方无感。
"""

from typing import Optional

import httpx
import logfire

from api.core.env_config import rbac_config
from api.logger.logger import log_span

from .constants import (
    AUTHORIZATION_HEADER,
    BEARER_PREFIX,
    DEFAULT_CONNECT_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    ENFORCE_PATH,
    HEALTH_PATH,
    OWNER_QUERY_PARAM,
    POLICIES_PATH,
    READY_PATH,
    ROLE_ASSIGNMENTS_PATH,
)
from .data_model import (
    EnforceResponse,
    PolicyEntry,
    RoleAssignmentEntry,
    StatusResponse,
)
from .exceptions import (
    RBACBadRequestError,
    RBACConnectionError,
    RBACError,
    RBACForbiddenError,
    RBACServerError,
    RBACUnauthorizedError,
)


class RBACClient:
    """IDIOT_RBAC 服务 HTTP 客户端"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        """
        Args:
            base_url: RBAC 服务 base_url，默认取 ``rbac_config.rbac_service_base_url``。
            token: Bearer Token，默认取 ``rbac_config`` 中配置的 token（未配置则为 None）。
                鉴权类接口在 token 缺失时会被服务端返回 401。
            timeout: 请求超时（秒）。
        """
        self.base_url = (base_url or rbac_config.rbac_service_base_url).rstrip("/")
        if token is None:
            token_value = rbac_config.rbac_service_token_value
            token = token_value.get_secret_value() if token_value is not None else None
        self.token = token
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端，默认注入鉴权头（若配置了 token）"""
        if self._client is None or self._client.is_closed:
            headers = {}
            if self.token:
                headers[AUTHORIZATION_HEADER] = f"{BEARER_PREFIX}{self.token}"
            self._client = httpx.AsyncClient(timeout=self.timeout, headers=headers)
        return self._client

    async def close(self) -> None:
        """关闭 HTTP 客户端（建议在应用 shutdown 时调用）"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ============================================================
    # 内部：请求与错误映射
    # ============================================================

    @staticmethod
    def _raise_for_status(response: httpx.Response, method: str, path: str) -> httpx.Response:
        """按 RBAC 统一错误结构（{"error", "message"}）将非成功响应映射为异常"""
        if response.is_success:
            return response
        try:
            body = response.json()
            error_type = body.get("error", "")
            message = body.get("message", response.text)
        except Exception:
            error_type = ""
            message = response.text
        detail = f"{method} {path} -> {response.status_code} {error_type}: {message}"
        if response.status_code == 400:
            logfire.warning(detail)
            raise RBACBadRequestError(detail)
        if response.status_code == 401:
            logfire.warning(detail)
            raise RBACUnauthorizedError(detail)
        if response.status_code == 403:
            logfire.warning(detail)
            raise RBACForbiddenError(detail)
        if response.status_code >= 500:
            logfire.error(detail)
            raise RBACServerError(detail)
        logfire.warning(detail)
        raise RBACError(detail)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> httpx.Response:
        """发送请求并处理错误映射。

        连接级错误（ConnectError / ConnectTimeout）会按 ``DEFAULT_CONNECT_RETRIES`` 重试，
        以应对 headless 服务中个别 Pod 暂时不可达的情况；其余传输错误与 HTTP 错误码
        通过 :meth:`_raise_for_status` 映射为对应异常。
        """
        client = await self._get_client()
        url = f"{self.base_url}{path}"
        attempts = DEFAULT_CONNECT_RETRIES + 1
        last_connect_exc: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                response = await client.request(method, url, json=json, params=params)
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                last_connect_exc = e
                logfire.warning(
                    f"RBAC 连接失败，重试 {attempt}/{attempts}: {method} {path}: {e}"
                )
                continue
            except httpx.RequestError as e:
                logfire.error(f"RBAC 请求错误 {method} {path}: {e}")
                raise RBACConnectionError(f"RBAC request error: {method} {path}: {e}") from e
            return self._raise_for_status(response, method, path)
        detail = (
            f"RBAC connection failed after {attempts} attempts: {method} {path}: "
            f"{last_connect_exc}"
        )
        logfire.error(detail)
        raise RBACConnectionError(detail) from last_connect_exc

    # ============================================================
    # 健康检查（无需鉴权）
    # ============================================================

    @log_span("RBAC 存活检查")
    async def health(self) -> bool:
        """存活探针（liveness），返回是否 200"""
        client = await self._get_client()
        try:
            response = await client.get(f"{self.base_url}{HEALTH_PATH}")
            return response.status_code == 200
        except httpx.RequestError as e:
            logfire.warning(f"RBAC health check failed: {e}")
            return False

    @log_span("RBAC 就绪检查")
    async def ready(self) -> bool:
        """就绪探针（readiness），返回 Enforcer 是否就绪且数据库连通"""
        client = await self._get_client()
        try:
            response = await client.get(f"{self.base_url}{READY_PATH}")
            return response.status_code == 200
        except httpx.RequestError as e:
            logfire.warning(f"RBAC ready check failed: {e}")
            return False

    # ============================================================
    # 鉴权判定
    # ============================================================

    @log_span(
        "RBAC 鉴权判定",
        args_captured_as_tags=["sub", "owner", "project", "obj", "act"],
    )
    async def enforce(
        self,
        sub: str,
        owner: str,
        project: str,
        obj: str,
        act: str,
        *,
        explain: bool = False,
    ) -> EnforceResponse:
        """
        执行一次 deny-overrides 权限判定。

        Args:
            sub: 请求主体（用户标识）
            owner: 资源所有者；``"*"`` 表示全局判定
            project: 项目名
            obj: 被访问对象（支持 keyMatch 模式）
            act: 操作
            explain: 是否返回命中的策略规则

        Returns:
            EnforceResponse: 是否放行（及可选的命中规则）

        Raises:
            RBACError: 鉴权服务调用失败
        """
        body = {
            "sub": sub,
            "owner": owner,
            "project": project,
            "obj": obj,
            "act": act,
            "explain": explain,
        }
        response = await self._request("POST", ENFORCE_PATH, json=body)
        return EnforceResponse(**response.json())

    # ============================================================
    # 策略管理（Casbin p 策略）
    # ============================================================

    @log_span("RBAC 新增策略", args_captured_as_tags=["owner"])
    async def create_policy(self, entry: PolicyEntry) -> StatusResponse:
        """新增一条策略"""
        response = await self._request("POST", POLICIES_PATH, json=entry.model_dump())
        return StatusResponse(**response.json())

    @log_span("RBAC 查询策略", args_captured_as_tags=["owner"])
    async def list_policies(self, owner: Optional[str] = None) -> list[PolicyEntry]:
        """
        查询策略。不传 owner 或传 ``"*"`` 时仅返回全局策略；
        传入具体 owner 时返回该 owner 的策略并附带全局策略。
        """
        params = {OWNER_QUERY_PARAM: owner} if owner is not None else None
        response = await self._request("GET", POLICIES_PATH, params=params)
        return [PolicyEntry(**item) for item in response.json()]

    @log_span("RBAC 删除策略", args_captured_as_tags=["owner"])
    async def delete_policy(self, entry: PolicyEntry) -> StatusResponse:
        """按策略完整匹配删除一条策略"""
        response = await self._request("DELETE", POLICIES_PATH, json=entry.model_dump())
        return StatusResponse(**response.json())

    # ============================================================
    # 角色分配（Casbin g 分组策略）
    # ============================================================

    @log_span("RBAC 分配角色", args_captured_as_tags=["user", "role", "owner"])
    async def assign_role(self, user: str, role: str, owner: str) -> StatusResponse:
        """为用户分配一个角色"""
        entry = RoleAssignmentEntry(user=user, role=role, owner=owner)
        response = await self._request("POST", ROLE_ASSIGNMENTS_PATH, json=entry.model_dump())
        return StatusResponse(**response.json())

    @log_span("RBAC 查询角色分配", args_captured_as_tags=["owner"])
    async def list_role_assignments(self, owner: Optional[str] = None) -> list[RoleAssignmentEntry]:
        """
        查询角色分配。不传 owner 或传 ``"*"`` 时仅返回全局分配；
        传入具体 owner 时返回该 owner 的分配并附带全局分配。
        """
        params = {OWNER_QUERY_PARAM: owner} if owner is not None else None
        response = await self._request("GET", ROLE_ASSIGNMENTS_PATH, params=params)
        return [RoleAssignmentEntry(**item) for item in response.json()]

    @log_span("RBAC 删除角色分配", args_captured_as_tags=["user", "role", "owner"])
    async def remove_role_assignment(self, user: str, role: str, owner: str) -> StatusResponse:
        """按完整匹配删除一条角色分配"""
        entry = RoleAssignmentEntry(user=user, role=role, owner=owner)
        response = await self._request("DELETE", ROLE_ASSIGNMENTS_PATH, json=entry.model_dump())
        return StatusResponse(**response.json())


# ============================================================
# 全局客户端实例
# ============================================================

_rbac_client: Optional[RBACClient] = None


def get_rbac_client() -> RBACClient:
    """获取全局 RBAC 客户端实例（懒加载单例）"""
    global _rbac_client
    if _rbac_client is None:
        _rbac_client = RBACClient()
    return _rbac_client
