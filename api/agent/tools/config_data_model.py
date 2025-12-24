from typing import Any

from pydantic import BaseModel

class A(BaseModel):
    a: int
    b: str
class B(BaseModel):
    c: A
    d: float

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


def _remove_fields(obj: Any, fields_to_remove: list[str]) -> Any:
    """递归删除指定的字段"""
    if isinstance(obj, dict):
        new_obj = {}
        for key, value in obj.items():
            if key in fields_to_remove:
                continue  # 跳过指定的字段
            new_obj[key] = _remove_fields(value, fields_to_remove)
        return new_obj
    elif isinstance(obj, list):
        return [_remove_fields(item, fields_to_remove) for item in obj]
    else:
        return obj


class SessionToolConfigBase(BaseModel):
    enabled: bool
