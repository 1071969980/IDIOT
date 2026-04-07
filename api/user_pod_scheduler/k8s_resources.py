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
            "pathPattern": "${.pvc.name}",
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


@log_span("获取 PVC 关联的 PV 名称", args_captured_as_tags=["pvc_name"])
async def get_pv_name_from_pvc(pvc_name: str, namespace: str = K8S_NAMESPACE) -> str | None:
    """获取 PVC 关联的 PV 名称"""
    client = get_k8s_client()
    try:
        pvc = client.v1.read_namespaced_persistent_volume_claim(pvc_name, namespace)
        return pvc.spec.volume_name if pvc.spec.volume_name else None
    except ApiException as e:
        if e.status == 404:
            return None
        raise


@log_span("等待 PVC 删除完成", args_captured_as_tags=["pvc_name"])
async def wait_for_pvc_deleted(pvc_name: str, namespace: str = K8S_NAMESPACE, timeout_seconds: int = 60) -> bool:
    """等待 PVC 被完全删除"""
    client = get_k8s_client()
    start_time = asyncio.get_event_loop().time()

    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout_seconds:
            logfire.warning(f"Timeout waiting for PVC {pvc_name} to be deleted")
            return False

        try:
            client.v1.read_namespaced_persistent_volume_claim(pvc_name, namespace)
            logfire.debug(f"PVC {pvc_name} still exists, waiting...")
            await asyncio.sleep(2)
        except ApiException as e:
            if e.status == 404:
                logfire.info(f"PVC {pvc_name} deleted successfully")
                return True
            raise


@log_span("等待 PV 删除完成", args_captured_as_tags=["pv_name"])
async def wait_for_pv_deleted(pv_name: str, timeout_seconds: int = 120) -> bool:
    """等待 PV 被完全删除"""
    client = get_k8s_client()
    start_time = asyncio.get_event_loop().time()

    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout_seconds:
            logfire.warning(f"Timeout waiting for PV {pv_name} to be deleted")
            return False

        try:
            client.v1.read_persistent_volume(pv_name)
            logfire.debug(f"PV {pv_name} still exists, waiting...")
            await asyncio.sleep(2)
        except ApiException as e:
            if e.status == 404:
                logfire.info(f"PV {pv_name} deleted successfully")
                return True
            raise


@log_span("删除用户 K8S 资源", args_captured_as_tags=["user_id"])
async def delete_user_k8s_resources(user_id: UUID | str) -> bool:
    """删除用户所有 K8S 资源（Retain 策略，JuiceFS 数据保留）

    删除顺序：
    1. Pod       — 释放 PVC 使用，CSI Node 自动清理 Mount Pod
    2. 获取 PV 名 — 在 PVC 删除前获取
    3. PVC       — 删除后 PV 变为 Released（CSI 不调用 DeleteVolume，数据保留）
    4. 等待 PVC 删除完成
    5. PV        — 手动删除 Released PV（仅清理 K8s 元数据，不动 JuiceFS 数据）
    6. 等待 PV 删除完成
    7. StorageClass
    8. Secret
    """
    client = get_k8s_client()

    pod_name = get_string_var(StringVarName.K8S_User_POD_Name, user_id)
    pvc_name = get_string_var(StringVarName.K8S_JuiceFS_User_PVC_Name, user_id)
    sc_name = get_string_var(StringVarName.K8S_JuiceFS_User_Storage_Class_Name, user_id)
    secret_name = get_string_var(StringVarName.K8S_JuiceFS_User_Secret_Name, user_id)

    errors = []

    # 1. 删除 Pod
    try:
        client.v1.delete_namespaced_pod(pod_name, K8S_NAMESPACE)
        logfire.info(f"Pod {pod_name} deleted")
    except ApiException as e:
        if e.status != 404:
            errors.append(f"pod: {e}")

    # 2. 获取 PV 名称（在删除 PVC 之前）
    pv_name = await get_pv_name_from_pvc(pvc_name)

    # 3. 删除 PVC → PV 变为 Released，JuiceFS 数据保留
    try:
        client.v1.delete_namespaced_persistent_volume_claim(pvc_name, K8S_NAMESPACE)
        logfire.info(f"PVC {pvc_name} deleted")
    except ApiException as e:
        if e.status != 404:
            errors.append(f"pvc: {e}")

    # 4. 等待 PVC 删除完成
    if not await wait_for_pvc_deleted(pvc_name):
        errors.append(f"pvc: timeout waiting for PVC {pvc_name} to be deleted")

    # 5. 手动删除 PV（Retain 策略下不会自动删除）
    if pv_name:
        try:
            client.v1.delete_persistent_volume(pv_name)
            logfire.info(f"PV {pv_name} deleted manually")
        except ApiException as e:
            if e.status != 404:
                errors.append(f"pv: {e}")

        # 6. 等待 PV 删除完成
        if not await wait_for_pv_deleted(pv_name):
            errors.append(f"pv: timeout waiting for PV {pv_name} to be deleted")

    # 7. 删除 StorageClass
    try:
        client.storage.delete_storage_class(sc_name)
        logfire.info(f"StorageClass {sc_name} deleted")
    except ApiException as e:
        if e.status != 404:
            errors.append(f"storageclass: {e}")

    # 8. 删除 Secret
    try:
        client.v1.delete_namespaced_secret(secret_name, K8S_NAMESPACE)
        logfire.info(f"Secret {secret_name} deleted")
    except ApiException as e:
        if e.status != 404:
            errors.append(f"secret: {e}")

    if errors:
        logfire.error(f"Errors during resource deletion: {errors}")
        return False
    return True