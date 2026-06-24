"""IDIOT_RBAC 客户端异常层次

所有异常均继承自 ``RBACError``。客户端按 HTTP 状态码 / 错误类型映射到具体异常，
便于调用方按需捕获（例如鉴权失败、服务端错误等）。
"""


class RBACError(Exception):
    """RBAC 客户端基础异常"""


class RBACConnectionError(RBACError):
    """网络/连接/超时错误（请求未到达服务端或服务端无响应）"""


class RBACBadRequestError(RBACError):
    """请求参数错误（HTTP 400，error=bad_request）"""


class RBACUnauthorizedError(RBACError):
    """鉴权失败（HTTP 401，error=unauthorized），通常是 token 缺失或不匹配"""


class RBACForbiddenError(RBACError):
    """禁止操作（HTTP 403，error=forbidden），例如删除由文件定义的全局策略/分配"""


class RBACServerError(RBACError):
    """RBAC 服务端错误（HTTP 5xx，error=internal_error）"""


class RBACPermissionDenied(RBACError):
    """业务层权限拒绝

    由 :func:`api.rbac.util.require_access` 在 ``enforce`` 判定为 deny 时抛出，
    用于在业务流程中作为守卫子句中断执行。
    """
