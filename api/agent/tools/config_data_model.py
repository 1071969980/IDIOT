from typing import Any

from pydantic import BaseModel

def turn_pydantic_model_to_json_schema(model_class: type[BaseModel]) -> dict:
    d = model_class.model_json_schema()
    d.pop("description", None)

    # 只有存在 $defs 时才进行解引用
    if "$defs" in d:
        d = _dereference_schema(d)

    # 递归删除指定的字段 (title, additionalProperties)
    return _remove_fields(d, ["title", "additionalProperties"])


def _dereference_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """递归解引用 JSON Schema 中的 $defs 和 $ref"""
    result = schema.copy()

    # 如果是第一次调用，提取 defs
    defs: dict[str, Any] = result.pop("$defs") if "$defs" in result else {}

    def replace_refs(obj: Any) -> Any:
        if isinstance(obj, dict):
            # 如果整个字典只有一个 $ref 键，直接替换整个字典
            if len(obj) == 1 and "$ref" in obj:
                ref_value = obj["$ref"]
                if (isinstance(ref_value, str)
                        and ref_value.startswith("#/$defs/")):
                    ref_name = ref_value[8:]  # 移除 "#/$defs/" 前缀
                    if ref_name in defs:
                        return replace_refs(defs[ref_name])
                    else:
                        return obj

            # 否则，逐个处理字典中的键值对
            new_obj = {}
            for key, value in obj.items():
                if (key == "$ref" and isinstance(value, str)
                        and value.startswith("#/$defs/")):
                    ref_name = value[8:]  # 移除 "#/$defs/" 前缀
                    if ref_name in defs:
                        new_obj.update(replace_refs(defs[ref_name]))
                    else:
                        new_obj[key] = value
                else:
                    new_obj[key] = replace_refs(value)
            return new_obj
        elif isinstance(obj, list):
            return [replace_refs(item) for item in obj]
        else:
            return obj

    return replace_refs(result)


def _remove_fields(obj: Any, fields_to_remove: list[str], _parent_key: str | None = None) -> Any:
    """递归删除指定的字段

    注意：如果字段是 'properties' 的直接子字段，则跳过删除。
    例如：properties.title、properties.additionalProperties 会被保留。
    """
    if isinstance(obj, dict):
        new_obj = {}
        for key, value in obj.items():
            # 如果父键是 'properties'，则保留所有字段（跳过过滤）
            if _parent_key == "properties":
                new_obj[key] = _remove_fields(value, fields_to_remove, key)
            elif key in fields_to_remove:
                continue  # 跳过指定的字段
            else:
                new_obj[key] = _remove_fields(value, fields_to_remove, key)
        return new_obj
    elif isinstance(obj, list):
        return [_remove_fields(item, fields_to_remove, _parent_key) for item in obj]
    else:
        return obj


class SessionToolConfigBase(BaseModel):
    enabled: bool
