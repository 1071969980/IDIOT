"""IDIOT_RBAC 服务数据模型

字段名与 IDIOT_RBAC 的 JSON 协议完全一致（snake_case），因此 pydantic 默认即可
正确序列化 / 反序列化，无需额外 alias。详见
``IDIOT_RBAC/docs/api/idiot_rbac.apib``。
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# Casbin 策略效果（eft）：deny-overrides —— 任一 deny 命中即拒绝
PolicyEffect = Literal["allow", "deny"]


class PolicyEntry(BaseModel):
    """Casbin ``p`` 策略

    对应策略定义 ``p = sub_role, owner, project_pattern, obj_pattern, act, eft``。
    """

    sub_role: str = Field(
        ..., description="主体角色；空字符串表示无需角色（公开策略）"
    )
    owner: str = Field(
        ...,
        description="资源所有者，支持 keyMatch；'*' 表示全局策略（广播所有分表）",
    )
    project_pattern: str = Field(..., description="项目匹配模式（keyMatch）")
    obj_pattern: str = Field(..., description="对象匹配模式（keyMatch）")
    act: str = Field(..., description="操作匹配模式（keyMatch），'*' 表示任意操作")
    eft: PolicyEffect = Field(..., description="策略效果：allow / deny")


class RoleAssignmentEntry(BaseModel):
    """Casbin ``g`` 分组策略（角色分配）

    对应分组定义 ``g = _, _, _``（user, role, owner），将用户与角色在某个 owner 域内绑定。
    """

    user: str = Field(..., description="用户标识")
    role: str = Field(..., description="被分配的角色名")
    owner: str = Field(
        ..., description="所属 owner 域；'*' 表示全局分配（广播所有分表）"
    )


class EnforceRequest(BaseModel):
    """鉴权判定请求

    请求维度 ``sub, owner, project, obj, act``，owner/project/obj/act 均使用 keyMatch 匹配。
    """

    sub: str = Field(..., description="请求主体（用户标识）")
    owner: str = Field(..., description="资源所有者；'*' 表示全局判定")
    project: str = Field(..., description="项目名")
    obj: str = Field(..., description="被访问对象（支持 keyMatch 模式，如 /api/*）")
    act: str = Field(..., description="操作（如 read / write / *）")
    explain: bool = Field(
        default=False, description="是否返回命中的策略规则，默认 False"
    )


class EnforceResponse(BaseModel):
    """鉴权判定响应"""

    allow: bool = Field(..., description="是否放行")
    explain: Optional[list[list[str]]] = Field(
        default=None,
        description=(
            "命中的策略规则列表；仅当请求 explain=True 且（allow=True 或命中非空）时返回。"
            "每条规则为 [sub_role, owner, project_pattern, obj_pattern, act, eft]"
        ),
    )


class StatusResponse(BaseModel):
    """写操作（新增/删除）成功后的统一响应体"""

    status: str = Field(..., description="固定为 'ok'")
