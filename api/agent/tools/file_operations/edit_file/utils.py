def edit_string(string: str, old_text: str, new_text: str, replace_all: bool = False):
    """
    编辑字符串，替换指定文本

    Args:
        string: 原始字符串
        old_text: 要替换的文本
        new_text: 替换后的文本
        replace_all: 是否替换所有匹配项

    Returns:
        替换后的字符串

    Raises:
        ValueError: 如果 old_text 未找到或重复出现且 replace_all=False
    """
    index = string.find(old_text)
    if index == -1:
        raise ValueError("old_text not found in string")

    has_second_occurrence = string.find(old_text, index + 1) != -1
    if not replace_all and has_second_occurrence:
        raise ValueError("old_text found more than once in string")

    return string.replace(old_text, new_text)
