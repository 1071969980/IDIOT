
REPLACE_MARKER = "$replace"
DELETE_MARKER = "$delete"


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