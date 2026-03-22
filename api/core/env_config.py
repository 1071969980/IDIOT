"""集中化配置模块

提供 Kubernetes 命名空间和服务端点的配置管理。
支持通过环境变量覆盖默认值，实现多环境部署。
"""

from pydantic import computed_field
from pydantic_settings import BaseSettings


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


# 全局单例实例
namespace_config = NamespaceConfig()
service_config = ServiceConfig()