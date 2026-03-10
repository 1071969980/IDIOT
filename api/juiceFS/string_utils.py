from typing import TYPE_CHECKING
from enum import Enum
from uuid import UUID
from api.s3_FS import S3_ENDPOINT

from typing import Any


USER_POD_MOUNTING_PATH = "/juice"
USER_POD_SYSTEM_PATH = "/juice/sys"
USER_POD_PUBLIC_PATH = "/juice/pub"
USER_POD_PRIVATE_PATH = "/juice/priv"


class StringVarName(str, Enum):
    JuiceFS_Meta_Name = "JUICEFS_META_NAME"
    JuiceFS_User_OSS_Bucket_Name = "JUICEFS_USER_OSS_BUCKET_NAME"
    JuiceFS_User_OSS_Bucket_URL = "JUICEFS_USER_OSS_BUCKET_URL"
    JuiceFS_User_Metadata_DB_NAME = "JUICEFS_USER_METADATA_DB_NAME"
    JuiceFS_User_Metadata_DB_URL = "JUICEFS_USER_METADATA_DB_URL"
    K8S_JuiceFS_User_Secret_Name = "K8S_JUICEFS_USER_SECRET_NAME"
    K8S_JuiceFS_User_Storage_Class_Name = "K8S_JUICEFS_USER_STORAGE_CLASS_NAME"
    K8S_JuiceFS_User_PVC_Name = "K8S_JUICEFS_USER_PVC_NAME"
    K8S_JuiceFS_User_PV_Name = "K8S_JUICEFS_USER_PV_NAME"
    K8S_User_POD_Name = "K8S_USER_POD_NAME"

def get_string_var(var_name: StringVarName, user_id: UUID | str, **kwargs: dict[str, Any]) -> str:
    user_id_str = str(user_id)
    match var_name:
        case StringVarName.JuiceFS_Meta_Name:
            return f"juicefs-meta-{user_id_str}"
        case StringVarName.JuiceFS_User_OSS_Bucket_Name:
            return f"juicefs-user-{user_id_str}"
        case StringVarName.JuiceFS_User_OSS_Bucket_URL:
            return f"{S3_ENDPOINT}/juicefs-user-{user_id_str}"
        case StringVarName.JuiceFS_User_Metadata_DB_NAME:
            return f"juicefs-user-{user_id_str}"
        case StringVarName.JuiceFS_User_Metadata_DB_URL:
            return f"postgres://postgres:juicefs-postgres@juicefs-postgres:5432/juicefs-user-{user_id_str}"
        case StringVarName.K8S_JuiceFS_User_Secret_Name:
            return f"juicefs-secret-user-{user_id_str}"
        case StringVarName.K8S_JuiceFS_User_Storage_Class_Name:
            return f"juicefs-storage-class-user-{user_id_str}"
        case StringVarName.K8S_JuiceFS_User_PVC_Name:
            return f"juicefs-pvc-user-{user_id_str}"
        case StringVarName.K8S_JuiceFS_User_PV_Name:
            return f"juicefs-pv-user-{user_id_str}"
        case StringVarName.K8S_User_POD_Name:
            return f"user-space-pod-user-{user_id_str}"
        case _:
            raise ValueError(f"Invalid var_name: {var_name}")
