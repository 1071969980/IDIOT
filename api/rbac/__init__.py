"""IDIOT_RBAC 鉴权服务交互包

提供：
- :class:`RBACClient`：对 RBAC HTTP API 的原子方法封装；
- :mod:`api.rbac.util`：业务原子语义实用函数；
- :mod:`api.rbac.data_model` / :mod:`api.rbac.exceptions` / :mod:`api.rbac.constants`：
  数据模型、异常与字符串常量。

服务地址与鉴权 token 统一由 :mod:`api.core.env_config` 的 ``rbac_config`` 提供。
"""

from .client import RBACClient, get_rbac_client
from .constants import (
    ACTION_ANY,
    ADMIN_ROLE,
    AUTHORIZATION_HEADER,
    BEARER_PREFIX,
    DEFAULT_CONNECT_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    EFFECT_ALLOW,
    EFFECT_DENY,
    ENFORCE_PATH,
    GLOBAL_OWNER,
    HEALTH_PATH,
    OWNER_QUERY_PARAM,
    POLICIES_PATH,
    PROJECT_ANY,
    PUBLIC_ROLE,
    READY_PATH,
    ROLE_ASSIGNMENTS_PATH,
)
from .data_model import (
    EnforceRequest,
    EnforceResponse,
    PolicyEffect,
    PolicyEntry,
    RoleAssignmentEntry,
    StatusResponse,
)
from .exceptions import (
    RBACBadRequestError,
    RBACConnectionError,
    RBACError,
    RBACForbiddenError,
    RBACPermissionDenied,
    RBACServerError,
    RBACUnauthorizedError,
)
from .util import (
    bootstrap_owner,
    enforce_access,
    grant_role,
    is_admin,
    list_user_roles,
    require_access,
    revoke_role,
    set_public_access,
)

__all__ = [
    # client
    "RBACClient",
    "get_rbac_client",
    # constants
    "HEALTH_PATH",
    "READY_PATH",
    "ENFORCE_PATH",
    "POLICIES_PATH",
    "ROLE_ASSIGNMENTS_PATH",
    "OWNER_QUERY_PARAM",
    "AUTHORIZATION_HEADER",
    "BEARER_PREFIX",
    "EFFECT_ALLOW",
    "EFFECT_DENY",
    "GLOBAL_OWNER",
    "ACTION_ANY",
    "PROJECT_ANY",
    "PUBLIC_ROLE",
    "ADMIN_ROLE",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_CONNECT_RETRIES",
    # data models
    "PolicyEffect",
    "PolicyEntry",
    "RoleAssignmentEntry",
    "EnforceRequest",
    "EnforceResponse",
    "StatusResponse",
    # exceptions
    "RBACError",
    "RBACConnectionError",
    "RBACBadRequestError",
    "RBACUnauthorizedError",
    "RBACForbiddenError",
    "RBACServerError",
    "RBACPermissionDenied",
    # util
    "enforce_access",
    "require_access",
    "is_admin",
    "grant_role",
    "revoke_role",
    "list_user_roles",
    "set_public_access",
    "bootstrap_owner",
]
