"""用户文件系统工具函数"""

import stat
from pathlib import PurePosixPath

from fastapi import HTTPException, status

from api.juiceFS.string_utils import StringVarName, get_string_var


def get_meta_url(user_id: str) -> str:
    """获取用户的 JuiceFS meta_url"""
    return get_string_var(StringVarName.JuiceFS_User_Metadata_DB_URL, user_id)


def get_pvc_name(user_id: str) -> str:
    """获取用户的 PVC 名称"""
    return get_string_var(StringVarName.K8S_JuiceFS_User_PVC_Name, user_id)


def validate_and_build_path(user_input_path: str, pvc_name: str) -> str:
    """验证并构建安全的文件系统路径

    Args:
        user_input_path: 用户输入的相对路径（如 "/pub/file.txt" 或 "pub/file.txt"）
        pvc_name: 用户的 PVC 名称

    Returns:
        完整的安全路径，格式为 "/{pvc_name}/..."

    Raises:
        HTTPException: 路径包含非法字符或尝试路径遍历攻击
    """
    # 去除首尾空白
    user_input_path = user_input_path.strip()

    if not user_input_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="路径不能为空",
        )

    # 使用 PurePosixPath 进行路径规范化（防止 ../ 攻击）
    try:
        # PurePosixPath 会自动处理 .. 和 . 并规范化路径
        normalized = PurePosixPath(user_input_path)

        # 检查是否包含路径遍历（规范化后仍有 .. 说明试图逃逸）
        if ".." in str(normalized) or normalized.is_absolute():
            # 如果是绝对路径，去掉开头的 /
            if normalized.is_absolute():
                normalized = PurePosixPath(*normalized.parts[1:])

        # 再次检查是否有 ..
        parts = normalized.parts
        if any(part == ".." for part in parts):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="非法路径：不允许使用 '..'",
            )

        # 构建完整路径：/{pvc_name}/{normalized_path}
        safe_path = PurePosixPath("/") / pvc_name / normalized

        # 最终验证：确保路径以 /{pvc_name} 开头
        path_str = str(safe_path)
        if not path_str.startswith(f"/{pvc_name}"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="非法路径",
            )

        return path_str

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"路径格式错误: {e}",
        ) from e


def _is_dir_from_mode(st_mode: int) -> bool:
    """从 st_mode 判断是否为目录"""
    return stat.S_ISDIR(st_mode)


def _strip_pvc_prefix(path: str, pvc_name: str) -> str:
    """移除路径中的 PVC 前缀，返回用户可见的相对路径"""
    prefix = f"/{pvc_name}"
    if path.startswith(prefix):
        return path[len(prefix):] or "/"
    return path