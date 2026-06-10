
from typing import Any

REPLACE_MARKER = "$replace"
DELETE_MARKER = "$delete"
_MISSING = object()


def deep_update_dict(original: dict, update_with: dict) -> dict:
    """
    递归地将 update_with 中的内容合并到 original 字典中。

    对于嵌套的字典会进行深度合并，其余类型直接覆盖。

    特殊标记：
    - {"$delete": True} — 从 original 中删除对应的键
    - {"$replace": value} — 用 value 整体替换该键，停止递归

    注意：该函数会就地修改 original 字典，并返回它。
    """
    keys_to_delete = []

    for key, value in update_with.items():
        if isinstance(value, dict):
            if value.get(DELETE_MARKER) is True:
                keys_to_delete.append(key)
            elif REPLACE_MARKER in value:
                original[key] = value[REPLACE_MARKER]
            elif isinstance(original.get(key), dict):
                deep_update_dict(original[key], value)
            else:
                original[key] = value
        else:
            original[key] = value

    for key in keys_to_delete:
        original.pop(key, None)

    return original


def resolve_scope_value(scope_def: dict[str, Any], key_paths: list[str]) -> Any:
    """按优先级从 scope_def 解析值。

    依次尝试 key_paths 中的每个路径（支持点号分隔的嵌套路径），
    返回第一个找到的值。所有路径均未找到时抛出 KeyError。
    """
    for path in key_paths:
        value = _get_by_path(scope_def, path, _MISSING)
        if value is not _MISSING:
            return value
    msg = f"scope_def 中未找到匹配的键路径: {key_paths}"
    raise KeyError(msg)


def _get_by_path(d: dict, path: str, default: Any) -> Any:
    """按点号分隔路径获取嵌套字典值。"""
    keys = path.split(".")
    current: Any = d
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current