"""Kubernetes 客户端封装"""

from typing import Optional
import logfire

from kubernetes import config
from kubernetes.client import CoreV1Api, StorageV1Api


class K8SClient:
    """Kubernetes 客户端单例"""

    _instance: Optional['K8SClient'] = None
    _v1_api: Optional[CoreV1Api] = None
    _storage_api: Optional[StorageV1Api] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _ensure_initialized(self):
        """确保客户端已初始化"""
        if not self._initialized:
            self._init_client()
            self._initialized = True

    def _init_client(self):
        """初始化 Kubernetes 客户端"""
        try:
            # 尝试加载集群内配置
            config.load_incluster_config()
            logfire.info("Loaded Kubernetes in-cluster config")
        except config.ConfigException:
            # 失败则加载 kubeconfig
            try:
                config.load_kube_config()
                logfire.info("Loaded Kubernetes kubeconfig")
            except config.ConfigException as e:
                logfire.error(f"Failed to load Kubernetes config: {e}")
                raise

        self._v1_api = CoreV1Api()
        self._storage_api = StorageV1Api()

    @property
    def v1(self) -> CoreV1Api:
        """获取 CoreV1Api 实例"""
        self._ensure_initialized()
        return self._v1_api

    @property
    def storage(self) -> StorageV1Api:
        """获取 StorageV1Api 实例"""
        self._ensure_initialized()
        return self._storage_api


def get_k8s_client() -> K8SClient:
    """获取 K8S 客户端实例"""
    return K8SClient()