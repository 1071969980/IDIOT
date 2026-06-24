"""IDIOT_RBAC 服务交互常量定义

仅存放端点路径、请求头、策略效果与通配符等字符串常量。
服务地址（base_url）与鉴权 token 由统一配置模块
``api.core.env_config`` 提供，不在此处硬编码。
"""

# ============================================================
# 端点路径
# ============================================================

# 健康检查（无需鉴权）
HEALTH_PATH = "/healthz"  # 存活探针（liveness）
READY_PATH = "/readyz"  # 就绪探针（readiness）

# 鉴权与策略管理（需 Bearer Token）
ENFORCE_PATH = "/api/v1/enforce"  # 权限判定
POLICIES_PATH = "/api/v1/policies"  # 策略增删查
ROLE_ASSIGNMENTS_PATH = "/api/v1/role-assignments"  # 角色分配增删查

# 查询参数名
OWNER_QUERY_PARAM = "owner"

# ============================================================
# 认证
# ============================================================

AUTHORIZATION_HEADER = "Authorization"
BEARER_PREFIX = "Bearer "

# ============================================================
# 策略效果 / 通配符 / 占位
# ============================================================

# Casbin 策略效果（eft 字段取值）
EFFECT_ALLOW = "allow"
EFFECT_DENY = "deny"

# owner 维度通配符：owner 为 "*" 时表示全局策略（广播写入所有分表）
GLOBAL_OWNER = "*"

# 操作维度通配符：act 为 "*" 时表示任意操作
ACTION_ANY = "*"

# 项目维度通配符：project_pattern 为 "*" 时匹配任意项目
PROJECT_ANY = "*"

# 公开角色占位：sub_role 为空字符串表示无需任何角色即可匹配（公开访问）
PUBLIC_ROLE = ""

# 默认管理员角色名（对应 IDIOT_RBAC 默认全局策略 p, admin, *, *, *, *, allow）
ADMIN_ROLE = "admin"

# ============================================================
# 默认连接参数
# ============================================================

# 默认请求超时（秒）
DEFAULT_TIMEOUT_SECONDS = 10.0

# 连接级失败时的重试次数。
# IDIOT_RBAC 为 headless StatefulSet（clusterIP: None），DNS 会返回多个 Pod IP，
# 连接到某个不可达 Pod 时重试大概率命中其它健康 Pod。
DEFAULT_CONNECT_RETRIES = 2
