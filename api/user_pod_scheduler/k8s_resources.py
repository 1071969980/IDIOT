"""Kubernetes 资源创建和管理"""

import asyncio
import logfire
from uuid import UUID
from typing import Optional

from kubernetes.client import (
    V1Secret,
    V1ObjectMeta,
    V1StorageClass,
    V1PersistentVolumeClaim,
    V1PersistentVolumeClaimSpec,
    V1TypedLocalObjectReference,
    V1Pod,
    V1PodSpec,
    V1Container,
    V1Volume,
    V1PersistentVolumeClaimVolumeSource,
    V1VolumeMount,
    V1ResourceRequirements,
    ApiException,
)

from api.juiceFS.string_utils import StringVarName, get_string_var
from api.user_pod_scheduler.constants import (
    K8S_NAMESPACE,
    USER_POD_IMAGE,
    USER_POD_CONTAINER_NAME,
    JUICEFS_MOUNT_PATH,
    POD_STATUS_CHECK_INTERVAL_SECONDS,
)
from api.user_pod_scheduler.k8s_client import get_k8s_client
from api.logger.logger import log_span


@log_span("检查 K8S 资源是否存在", args_captured_as_tags=["resource_type", "resource_name"])
async def check_k8s_resource_exists(
    resource_type: str,
    resource_name: str,
    namespace: str = K8S_NAMESPACE
) -> bool:
    """检查 K8S 资源是否存在"""
    client = get_k8s_client()

    try:
        match resource_type:
            case "secret":
                client.v1.read_namespaced_secret(resource_name, namespace)
            case "storageclass":
                client.storage.read_storage_class(resource_name)
            case "pvc":
                client.v1.read_namespaced_persistent_volume_claim(resource_name, namespace)
            case "pod":
                client.v1.read_namespaced_pod(resource_name, namespace)
            case _:
                raise ValueError(f"Unknown resource type: {resource_type}")
        return True
    except ApiException as e:
        if e.status == 404:
            return False
        raise


@log_span("创建 JuiceFS Secret", args_captured_as_tags=["user_id"])
async def create_juicefs_secret(user_id: UUID | str) -> bool:
    """创建 JuiceFS Secret"""
    client = get_k8s_client()
    secret_name = get_string_var(StringVarName.K8S_JuiceFS_User_Secret_Name, user_id)
    meta_name = get_string_var(StringVarName.JuiceFS_Meta_Name, user_id)
    meta_url = get_string_var(StringVarName.JuiceFS_User_Metadata_DB_URL, user_id)

    secret = V1Secret(
        metadata=V1ObjectMeta(
            name=secret_name,
            namespace=K8S_NAMESPACE,
            labels={"juicefs.com/validate-secret": "true"}
        ),
        type="Opaque",
        string_data={
            "name": meta_name,
            "metaurl": meta_url,
        }
    )

    try:
        # 检查是否已存在
        if await check_k8s_resource_exists("secret", secret_name):
            logfire.info(f"Secret {secret_name} already exists")
            return True

        client.v1.create_namespaced_secret(K8S_NAMESPACE, secret)
        logfire.info(f"Secret {secret_name} created successfully")
        return True
    except ApiException as e:
        logfire.error(f"Failed to create secret: {e}")
        return False


@log_span("创建 StorageClass", args_captured_as_tags=["user_id"])
async def create_storage_class(user_id: UUID | str) -> bool:
    """创建 StorageClass"""
    client = get_k8s_client()
    sc_name = get_string_var(StringVarName.K8S_JuiceFS_User_Storage_Class_Name, user_id)
    secret_name = get_string_var(StringVarName.K8S_JuiceFS_User_Secret_Name, user_id)

    storage_class = V1StorageClass(
        metadata=V1ObjectMeta(
            name=sc_name,
        ),
        provisioner="csi.juicefs.com",
        parameters={
            "csi.storage.k8s.io/provisioner-secret-name": secret_name,
            "csi.storage.k8s.io/provisioner-secret-namespace": K8S_NAMESPACE,
            "csi.storage.k8s.io/node-publish-secret-name": secret_name,
            "csi.storage.k8s.io/node-publish-secret-namespace": K8S_NAMESPACE,
            "pathPattern": "${.pvc.namespace}-${.pvc.name}",
        },
        reclaim_policy="Retain"
    )

    try:
        if await check_k8s_resource_exists("storageclass", sc_name):
            logfire.info(f"StorageClass {sc_name} already exists")
            return True

        client.storage.create_storage_class(storage_class)
        logfire.info(f"StorageClass {sc_name} created successfully")
        return True
    except ApiException as e:
        logfire.error(f"Failed to create storage class: {e}")
        return False


@log_span("创建 PVC", args_captured_as_tags=["user_id"])
async def create_pvc(user_id: UUID | str) -> bool:
    """创建 PersistentVolumeClaim"""
    client = get_k8s_client()
    pvc_name = get_string_var(StringVarName.K8S_JuiceFS_User_PVC_Name, user_id)
    sc_name = get_string_var(StringVarName.K8S_JuiceFS_User_Storage_Class_Name, user_id)

    pvc = V1PersistentVolumeClaim(
        metadata=V1ObjectMeta(
            name=pvc_name,
            namespace=K8S_NAMESPACE,
        ),
        spec=V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteMany"],
            storage_class_name=sc_name,
            resources=V1ResourceRequirements(
                requests={"storage": "10Gi"}
            )
        )
    )

    try:
        if await check_k8s_resource_exists("pvc", pvc_name):
            logfire.info(f"PVC {pvc_name} already exists")
            return True

        client.v1.create_namespaced_persistent_volume_claim(K8S_NAMESPACE, pvc)
        logfire.info(f"PVC {pvc_name} created successfully")
        return True
    except ApiException as e:
        logfire.error(f"Failed to create PVC: {e}")
        return False


@log_span("创建用户 Pod", args_captured_as_tags=["user_id"])
async def create_user_pod(user_id: UUID | str) -> bool:
    """创建用户 Pod"""
    client = get_k8s_client()
    pod_name = get_string_var(StringVarName.K8S_User_POD_Name, user_id)
    pvc_name = get_string_var(StringVarName.K8S_JuiceFS_User_PVC_Name, user_id)
    volume_name = get_string_var(StringVarName.K8S_JuiceFS_User_PV_Name, user_id)

    pod = V1Pod(
        metadata=V1ObjectMeta(
            name=pod_name,
            namespace=K8S_NAMESPACE,
        ),
        spec=V1PodSpec(
            containers=[
                V1Container(
                    name=USER_POD_CONTAINER_NAME,
                    image=USER_POD_IMAGE,
                    command=["/bin/sh", "-c"],
                    args=["while true; do sleep 3600; done"],  # 保持容器运行
                    working_dir=JUICEFS_MOUNT_PATH,  # 设置工作目录为 JuiceFS 挂载路径
                    volume_mounts=[
                        V1VolumeMount(
                            name=volume_name,
                            mount_path=JUICEFS_MOUNT_PATH,
                            mount_propagation="HostToContainer"
                        )
                    ]
                )
            ],
            volumes=[
                V1Volume(
                    name=volume_name,
                    persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(
                        claim_name=pvc_name
                    )
                )
            ]
        )
    )

    try:
        if await check_k8s_resource_exists("pod", pod_name):
            logfire.info(f"Pod {pod_name} already exists")
            return True

        client.v1.create_namespaced_pod(K8S_NAMESPACE, pod)
        logfire.info(f"Pod {pod_name} created successfully")
        return True
    except ApiException as e:
        logfire.error(f"Failed to create pod: {e}")
        return False


@log_span("等待 Pod 就绪", args_captured_as_tags=["user_id"])
async def wait_for_pod_ready(
    user_id: UUID | str,
    timeout_seconds: int = 300
) -> tuple[bool, str]:
    """等待 Pod 进入 Running 状态"""
    client = get_k8s_client()
    pod_name = get_string_var(StringVarName.K8S_User_POD_Name, user_id)

    start_time = asyncio.get_event_loop().time()

    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout_seconds:
            return False, "Timeout waiting for pod to be ready"

        try:
            pod = client.v1.read_namespaced_pod_status(pod_name, K8S_NAMESPACE)
            phase = pod.status.phase

            if phase == "Running":
                return True, "Pod is running"
            elif phase in ["Failed", "Unknown"]:
                return False, f"Pod in unexpected state: {phase}"

            logfire.debug(f"Pod {pod_name} status: {phase}, waiting...")
            await asyncio.sleep(POD_STATUS_CHECK_INTERVAL_SECONDS)

        except ApiException as e:
            if e.status == 404:
                return False, "Pod not found"
            return False, f"Error checking pod status: {e}"


@log_span("获取 Pod 状态", args_captured_as_tags=["user_id"])
async def get_pod_status(user_id: UUID | str) -> dict:
    """获取 Pod 详细状态"""
    client = get_k8s_client()
    pod_name = get_string_var(StringVarName.K8S_User_POD_Name, user_id)

    try:
        pod = client.v1.read_namespaced_pod_status(pod_name, K8S_NAMESPACE)

        container_statuses = []
        if pod.status.container_statuses:
            for cs in pod.status.container_statuses:
                container_statuses.append({
                    "name": cs.name,
                    "ready": cs.ready,
                    "restart_count": cs.restart_count,
                    "state": str(cs.state),
                })

        return {
            "exists": True,
            "phase": pod.status.phase,
            "pod_ip": pod.status.pod_ip,
            "host_ip": pod.status.host_ip,
            "start_time": pod.status.start_time.isoformat() if pod.status.start_time else None,
            "container_statuses": container_statuses,
        }
    except ApiException as e:
        if e.status == 404:
            return {"exists": False, "phase": None}
        raise


@log_span("删除用户 Pod", args_captured_as_tags=["user_id"])
async def delete_user_pod(user_id: UUID | str) -> bool:
    """删除用户 Pod"""
    client = get_k8s_client()
    pod_name = get_string_var(StringVarName.K8S_User_POD_Name, user_id)

    try:
        client.v1.delete_namespaced_pod(pod_name, K8S_NAMESPACE)
        logfire.info(f"Pod {pod_name} deleted")
        return True
    except ApiException as e:
        if e.status == 404:
            return True
        logfire.error(f"Failed to delete pod: {e}")
        return False


@log_span("删除用户 K8S 资源", args_captured_as_tags=["user_id"])
async def delete_user_k8s_resources(user_id: UUID | str) -> bool:
    """删除用户所有 K8S 资源"""
    client = get_k8s_client()

    pod_name = get_string_var(StringVarName.K8S_User_POD_Name, user_id)
    pvc_name = get_string_var(StringVarName.K8S_JuiceFS_User_PVC_Name, user_id)
    sc_name = get_string_var(StringVarName.K8S_JuiceFS_User_Storage_Class_Name, user_id)
    secret_name = get_string_var(StringVarName.K8S_JuiceFS_User_Secret_Name, user_id)

    errors = []

    # 按依赖顺序删除：Pod -> PVC -> StorageClass -> Secret
    delete_operations = [
        ("pod", pod_name, lambda n: client.v1.delete_namespaced_pod(n, K8S_NAMESPACE)),
        ("pvc", pvc_name, lambda n: client.v1.delete_namespaced_persistent_volume_claim(n, K8S_NAMESPACE)),
        ("storageclass", sc_name, lambda n: client.storage.delete_storage_class(n)),
        ("secret", secret_name, lambda n: client.v1.delete_namespaced_secret(n, K8S_NAMESPACE)),
    ]

    for resource_type, name, delete_func in delete_operations:
        try:
            delete_func(name)
            logfire.info(f"{resource_type} {name} deleted")
        except ApiException as e:
            if e.status != 404:
                errors.append(f"{resource_type}: {e}")

    if errors:
        logfire.error(f"Errors during resource deletion: {errors}")
        return False
    return True