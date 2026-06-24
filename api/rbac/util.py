"""RBAC 业务原子语义实用函数（草拟）

每个函数接受可选的 ``client`` 实例，缺省使用全局单例 :func:`get_rbac_client`。
这组语义为草拟，后续可按真实业务调整。
"""

from typing import Optional

from .client import RBACClient, get_rbac_client
from .constants import (
    ACTION_ANY,
    ADMIN_ROLE,
    EFFECT_ALLOW,
    GLOBAL_OWNER,
    PROJECT_ANY,
    PUBLIC_ROLE,
)
from .data_model import PolicyEffect, PolicyEntry
from .exceptions import RBACPermissionDenied


def _resolve_client(client: Optional[RBACClient]) -> RBACClient:
    """解析客户端实例：传入则用传入的，否则使用全局单例"""
    return client if client is not None else get_rbac_client()


async def enforce_access(
    sub: str,
    owner: str,
    project: str,
    obj: str,
    act: str,
    *,
    client: Optional[RBACClient] = None,
) -> bool:
    """布尔放行门：执行一次鉴权判定并返回是否放行"""
    c = _resolve_client(client)
    response = await c.enforce(sub, owner, project, obj, act)
    return response.allow


async def require_access(
    sub: str,
    owner: str,
    project: str,
    obj: str,
    act: str,
    *,
    client: Optional[RBACClient] = None,
) -> None:
    """权限守卫：判定为 deny 时抛出 :class:`RBACPermissionDenied`，放行则静默返回"""
    allowed = await enforce_access(sub, owner, project, obj, act, client=client)
    if not allowed:
        raise RBACPermissionDenied(
            f"权限拒绝: sub={sub} owner={owner} project={project} obj={obj} act={act}"
        )


async def is_admin(
    sub: str,
    owner: str,
    *,
    client: Optional[RBACClient] = None,
) -> bool:
    """草拟语义：以最宽泛的 obj/act 判定，命中通常意味着用户在该 owner 域内具备管理员级权限"""
    return await enforce_access(
        sub, owner, PROJECT_ANY, ACTION_ANY, ACTION_ANY, client=client
    )


async def grant_role(
    user: str,
    role: str,
    owner: str,
    *,
    client: Optional[RBACClient] = None,
) -> None:
    """为用户分配角色（assign_role 的业务别名）"""
    c = _resolve_client(client)
    await c.assign_role(user, role, owner)


async def revoke_role(
    user: str,
    role: str,
    owner: str,
    *,
    client: Optional[RBACClient] = None,
) -> None:
    """回收用户角色（remove_role_assignment 的业务别名）"""
    c = _resolve_client(client)
    await c.remove_role_assignment(user, role, owner)


async def list_user_roles(
    user: str,
    owner: str,
    *,
    client: Optional[RBACClient] = None,
) -> list[str]:
    """查询某用户在指定 owner 域内的全部角色"""
    c = _resolve_client(client)
    assignments = await c.list_role_assignments(owner=owner)
    return [a.role for a in assignments if a.user == user]


async def set_public_access(
    obj_pattern: str,
    *,
    act: str = "read",
    eft: PolicyEffect = EFFECT_ALLOW,
    owner: str = GLOBAL_OWNER,
    project_pattern: str = PROJECT_ANY,
    client: Optional[RBACClient] = None,
) -> None:
    """草拟语义：新增一条无需角色（公开）的访问策略

    Args:
        obj_pattern: 对象匹配模式，如 ``"/public/*"``
        act: 操作，默认 ``read``
        eft: 策略效果，默认 ``allow``
        owner: 所属 owner，默认全局（广播所有分表）
        project_pattern: 项目匹配模式，默认任意
    """
    c = _resolve_client(client)
    entry = PolicyEntry(
        sub_role=PUBLIC_ROLE,
        owner=owner,
        project_pattern=project_pattern,
        obj_pattern=obj_pattern,
        act=act,
        eft=eft,
    )
    await c.create_policy(entry)


async def bootstrap_owner(
    owner: str,
    admin_user: str,
    *,
    admin_role: str = ADMIN_ROLE,
    client: Optional[RBACClient] = None,
) -> None:
    """草拟语义：为新 owner 初始化——给 ``admin_user`` 分配管理员角色

    后续可扩展为同时写入默认公开策略等租户初始化逻辑。
    """
    c = _resolve_client(client)
    await c.assign_role(admin_user, admin_role, owner)
