"""集中化配置模块

提供 Kubernetes 命名空间、服务端点和应用配置的管理。
支持通过环境变量覆盖默认值，实现多环境部署。
"""

from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings


# ============================================================
# Kubernetes 配置
# ============================================================


class NamespaceConfig(BaseSettings):
    """命名空间配置

    字段名使用全称，方便代码库文本搜索。
    环境变量名与字段名完全一致。
    """

    k8s_namespace_app: str = "idiot"
    k8s_namespace_user_space: str = "idiot-user-space"
    k8s_namespace_user_space_storage: str = "idiot-user-space-storage"


class ServiceConfig(BaseSettings):
    """服务端点配置"""

    k8s_service_cluster_domain: str = "svc.cluster.local"
    k8s_service_juicefs_postgres_name: str = "juicefs-postgres"
    k8s_service_juicefs_minio_name: str = "juicefs-minio"

    @computed_field
    @property
    def juicefs_postgres_host(self) -> str:
        """获取 JuiceFS PostgreSQL 服务的 FQDN"""
        ns = namespace_config.k8s_namespace_user_space_storage
        return f"{self.k8s_service_juicefs_postgres_name}.{ns}.{self.k8s_service_cluster_domain}"

    @computed_field
    @property
    def juicefs_minio_host(self) -> str:
        """获取 JuiceFS MinIO 服务的 FQDN"""
        ns = namespace_config.k8s_namespace_user_space_storage
        return f"{self.k8s_service_juicefs_minio_name}.{ns}.{self.k8s_service_cluster_domain}"


# ============================================================
# 存储/数据库配置
# ============================================================


class StorageConfig(BaseSettings):
    """存储/数据库配置"""

    # S3/MinIO 配置
    s3_endpoint: str = Field(default="http://minio:9000", alias="S3_ENDPOINT")
    minio_root_user: str = Field(default="minio", alias="MINIO_ROOT_USER")
    minio_root_password: SecretStr = Field(
        default=SecretStr("minio_password"), alias="MINIO_ROOT_PASSWORD"
    )

    # PostgreSQL 配置
    postgres_password: SecretStr = Field(
        default=SecretStr("postgres"), alias="POSTGRES_PASSWORD"
    )
    juicefs_postgres_password: SecretStr = Field(
        default=SecretStr("juicefs-postgres"), alias="JUICEFS_POSTGRES_PASSWORD"
    )

    @computed_field
    @property
    def minio_access_key(self) -> str:
        """MinIO 访问密钥（与 MINIO_ROOT_USER 相同）"""
        return self.minio_root_user

    @computed_field
    @property
    def minio_secret_key(self) -> str:
        """MinIO 密钥（明文，用于 boto3 客户端）"""
        return self.minio_root_password.get_secret_value()

# ============================================================
# LLM/AI 服务配置
# ============================================================


class LLMServiceConfig(BaseSettings):
    """LLM/AI 服务配置

    必填字段使用 @property 实现延迟加载，
    仅在实际访问时才检查环境变量是否存在。
    """

    # 内部字段存储环境变量值（可选，默认 None）
    dashscope_api_key_value: Optional[SecretStr] = Field(default=None, alias="DASHSCOPE_API_KEY")
    deepseek_api_key_value: Optional[SecretStr] = Field(default=None, alias="DEEPSEEK_API_KEY")
    zhipu_api_key_value: Optional[SecretStr] = Field(default=None, alias="ZHIPU_API_KEY")
    langfuse_secret_key_value: Optional[SecretStr] = Field(default=None, alias="LANGFUSE_SECRET_KEY")
    langfuse_public_key_value: Optional[SecretStr] = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_host_value: Optional[str] = Field(default=None, alias="LANGFUSE_HOST")
    sat_service_url_value: Optional[str] = Field(default=None, alias="SAT_SERVICE_URL")

    @property
    def dashscope_api_key(self) -> SecretStr:
        """通义千问 API Key"""
        if self.dashscope_api_key_value is None:
            raise ValueError("DASHSCOPE_API_KEY is not set")
        return self.dashscope_api_key_value

    @property
    def deepseek_api_key(self) -> SecretStr:
        """DeepSeek API Key"""
        if self.deepseek_api_key_value is None:
            raise ValueError("DEEPSEEK_API_KEY is not set")
        return self.deepseek_api_key_value

    @property
    def zhipu_api_key(self) -> SecretStr:
        """智谱 API Key"""
        if self.zhipu_api_key_value is None:
            raise ValueError("ZHIPU_API_KEY is not set")
        return self.zhipu_api_key_value

    @property
    def langfuse_secret_key(self) -> SecretStr:
        """Langfuse 私钥"""
        if self.langfuse_secret_key_value is None:
            raise ValueError("LANGFUSE_SECRET_KEY is not set")
        return self.langfuse_secret_key_value

    @property
    def langfuse_public_key(self) -> SecretStr:
        """Langfuse 公钥"""
        if self.langfuse_public_key_value is None:
            raise ValueError("LANGFUSE_PUBLIC_KEY is not set")
        return self.langfuse_public_key_value

    @property
    def langfuse_host(self) -> str:
        """Langfuse 主机地址"""
        if self.langfuse_host_value is None:
            raise ValueError("LANGFUSE_HOST is not set")
        return self.langfuse_host_value

    @property
    def sat_service_url(self) -> str:
        """SAT 服务地址"""
        if self.sat_service_url_value is None:
            raise ValueError("SAT_SERVICE_URL is not set")
        return self.sat_service_url_value

# ============================================================
# 认证配置
# ============================================================


class AuthConfig(BaseSettings):
    """认证配置"""

    # 内部字段存储必填环境变量值（可选，默认 None）
    jwt_secret_key_value: Optional[SecretStr] = Field(default=None, alias="JWT_SECRET_KEY")

    # 可选字段（有默认值）
    auth_token_cookie_name: str = Field(
        default="auth_token", alias="AUTH_TOKEN_COOKIE_NAME"
    )
    remember_me_expire_days: int = Field(default=30, alias="REMEMBER_ME_EXPIRE_DAYS")
    remember_me_cookie_domain: str | None = Field(
        default=None, alias="REMEMBER_ME_COOKIE_DOMAIN"
    )
    remember_me_cookie_secure: bool = Field(
        default=True, alias="REMEMBER_ME_COOKIE_SECURE"
    )
    remember_me_cookie_httponly: bool = Field(
        default=True, alias="REMEMBER_ME_COOKIE_HTTPONLY"
    )
    remember_me_cookie_samesite: str = Field(
        default="lax", alias="REMEMBER_ME_COOKIE_SAMESITE"
    )

    @property
    def jwt_secret_key(self) -> SecretStr:
        """JWT 签名密钥"""
        if self.jwt_secret_key_value is None:
            raise ValueError("JWT_SECRET_KEY is not set")
        return self.jwt_secret_key_value


# ============================================================
# 用户 Pod 调度器配置
# ============================================================


class UserPodConfig(BaseSettings):
    """用户 Pod 调度器配置"""

    # 内部字段存储必填环境变量值（可选，默认 None）
    user_pod_image_value: Optional[str] = Field(default=None, alias="USER_POD_IMAGE")

    @property
    def user_pod_image(self) -> str:
        """用户 Pod 镜像地址"""
        if self.user_pod_image_value is None:
            raise ValueError("USER_POD_IMAGE is not set")
        return self.user_pod_image_value


# ============================================================
# 日志/追踪配置
# ============================================================


class LoggingConfig(BaseSettings):
    """日志/追踪配置"""

    logfire_log_endpoint: str | None = Field(
        default=None, alias="LOGFIRE_LOG_ENDPOINT"
    )

    @computed_field
    @property
    def otel_exporter_otlp_endpoint(self) -> str | None:
        """OTEL 导出端点（与 LOGFIRE_LOG_ENDPOINT 相同）"""
        return self.logfire_log_endpoint


# ============================================================
# 调试配置
# ============================================================


class DebugConfig(BaseSettings):
    """调试配置"""

    api_debug: bool = Field(default=False, alias="API_DEBUG")
    api_debug_port: int = Field(default=5678, alias="API_DEBUG_PORT")


# ============================================================
# 应用基础配置
# ============================================================


class AppConfig(BaseSettings):
    """应用基础配置"""

    cache_dir: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent.absolute(),
        alias="CACHE_DIR",
    )


# ============================================================
# 全局单例实例
# ============================================================

namespace_config = NamespaceConfig()
service_config = ServiceConfig()
storage_config = StorageConfig()
llm_service_config = LLMServiceConfig()
auth_config = AuthConfig()
user_pod_config = UserPodConfig()
logging_config = LoggingConfig()
debug_config = DebugConfig()
app_config = AppConfig()