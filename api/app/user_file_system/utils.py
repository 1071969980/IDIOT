"""用户文件系统工具函数

提供路径验证和构建功能，适配 FastAPI HTTP 异常。
"""

from fastapi import HTTPException, status

from api.juiceFS.path_utils import (
    get_meta_url,
    get_pvc_name,
    is_dir_from_mode,
    strip_pvc_prefix,
    validate_and_build_path as _validate_and_build_path,
)

__all__ = [
    "get_meta_url",
    "get_pvc_name",
    "is_dir_from_mode",
    "strip_pvc_prefix",
    "validate_and_build_path",
]


def validate_and_build_path(user_input_path: str, pvc_name: str) -> str:
    """验证并构建安全的文件系统路径

    包装 api.juiceFS.path_utils.validate_and_build_path，
    将 ValueError 转换为 HTTPException 以适配 FastAPI 端点。

    Args:
        user_input_path: 用户输入的相对路径
        pvc_name: 用户的 PVC 名称

    Returns:
        完整的安全路径

    Raises:
        HTTPException: 路径无效时
    """
    try:
        return _validate_and_build_path(user_input_path, pvc_name)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e