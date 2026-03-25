"""JuiceFS 路径工具函数

提供路径验证、构建和用户相关的工具函数。
这些函数可用于多个层级，不依赖 FastAPI 等框架特定类型。
"""

import stat
from pathlib import PurePosixPath

from api.juiceFS.string_utils import StringVarName, get_string_var


def get_meta_url(user_id: str) -> str:
    """获取用户的 JuiceFS meta_url

    Args:
        user_id: 用户 ID

    Returns:
        JuiceFS 元数据连接 URL
    """
    return get_string_var(StringVarName.JuiceFS_User_Metadata_DB_URL, user_id)


def get_pvc_name(user_id: str) -> str:
    """获取用户的 PVC 名称

    Args:
        user_id: 用户 ID

    Returns:
        用户 PVC 名称
    """
    return get_string_var(StringVarName.K8S_JuiceFS_User_PVC_Name, user_id)


def validate_and_build_path(user_input_path: str, pvc_name: str) -> str:
    """验证并构建安全的 JuiceFS 路径

    对用户输入的路径进行安全验证，防止路径遍历攻击，
    并构建带有 PVC 前缀的完整路径。

    Args:
        user_input_path: 用户输入的相对路径（如 "/pub/file.txt" 或 "pub/file.txt"）
        pvc_name: 用户的 PVC 名称

    Returns:
        完整的安全路径，格式为 "/{pvc_name}/..."

    Raises:
        ValueError: 路径为空、包含非法字符或尝试路径遍历攻击
    """
    # 去除首尾空白
    user_input_path = user_input_path.strip()

    if not user_input_path:
        raise ValueError("路径不能为空")

    # 使用 PurePosixPath 进行路径规范化（防止 ../ 攻击）
    try:
        # PurePosixPath 会自动处理 .. 和 . 并规范化路径
        normalized = PurePosixPath(user_input_path)

        # 如果是绝对路径，去掉开头的 /
        if normalized.is_absolute():
            normalized = PurePosixPath(*normalized.parts[1:])

        # 检查是否包含路径遍历（规范化后仍有 .. 说明试图逃逸）
        if ".." in str(normalized):
            error_msg = "非法路径：不允许使用 '..'"
            raise ValueError(error_msg)

        # 再次检查是否有 ..
        parts = normalized.parts
        if any(part == ".." for part in parts):
            error_msg = "非法路径：不允许使用 '..'"
            raise ValueError(error_msg)

        # 构建完整路径：/{pvc_name}/{normalized_path}
        safe_path = PurePosixPath("/") / pvc_name / normalized

        # 最终验证：确保路径以 /{pvc_name} 开头
        path_str = str(safe_path)
        if not path_str.startswith(f"/{pvc_name}"):
            raise ValueError("非法路径")

        return path_str

    except ValueError:
        raise
    except Exception as e:
        error_msg = f"路径格式错误: {e}"
        raise ValueError(error_msg) from e


def strip_pvc_prefix(path: str, pvc_name: str) -> str:
    """移除路径中的 PVC 前缀，返回用户可见的相对路径

    Args:
        path: 完整路径（如 "/pvc-name/pub/file.txt"）
        pvc_name: PVC 名称

    Returns:
        用户可见的相对路径（如 "/pub/file.txt"）
    """
    prefix = f"/{pvc_name}"
    if path.startswith(prefix):
        return path[len(prefix):] or "/"
    return path


def is_dir_from_mode(st_mode: int) -> bool:
    """从 st_mode 判断是否为目录

    Args:
        st_mode: 文件模式位

    Returns:
        True 如果是目录，否则 False
    """
    return stat.S_ISDIR(st_mode)
