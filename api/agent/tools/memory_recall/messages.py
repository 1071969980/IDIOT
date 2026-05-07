"""memory_recall 工具的消息模板"""

import ujson

from api.agent.xml_marks_def import (
    TOOL_DISCOVERY_RESULT_BLOCK_START,
    TOOL_DISCOVERY_RESULT_BLOCK_END,
)

from .config_data_model import GENERATION_TOOL_PARAM


def build_recall_work_requirements() -> str:
    """构建记忆召回工作要求。"""
    return (
        "## 记忆召回任务\n\n"
        "你是记忆召回 Agent。你的任务是根据当前上下文，从记忆文件系统中检索与当前任务相关的记忆内容，"
        "然后使用 return_memory_recall 工具将检索到的内容注入到主 Agent 的上下文中。\n\n"
        "工作流程：\n"
        "1. 先阅读下方提供的 MEMORY.md 索引文件，了解可用的记忆条目及其所在目录\n"
        "2. 使用 read_file 工具读取相关记忆文件的完整内容\n"
        "3. 调用 return_memory_recall 工具，将相关记忆内容推送到 major Marker\n"
        "4. 完成推送后，你可以停止\n\n"
        "注意：只召回与当前任务确实相关的记忆，不要盲目召回所有内容。"
    )


def format_recall_tool_param_disclosure() -> str:
    """格式化渲染 GENERATION_TOOL_PARAM 为文本。"""
    func_def = GENERATION_TOOL_PARAM["function"]
    return (
        f"{TOOL_DISCOVERY_RESULT_BLOCK_START}\n"
        f"{ujson.dumps(func_def, ensure_ascii=False)}\n"
        f"{TOOL_DISCOVERY_RESULT_BLOCK_END}"
    )


def build_recall_context_parts(memory_indices: list[tuple[str, str]]) -> list[str]:
    """组装记忆召回上下文消息的各部分。

    Args:
        memory_indices: 每个元素为 (directory_path, memory_md_content)。
    """
    parts = [build_recall_work_requirements()]

    if memory_indices:
        indices_text = "\n\n".join(
            f"### 记忆目录: {dir_path}\n{content}"
            for dir_path, content in memory_indices
        )
        parts.append(indices_text)
    else:
        parts.append("当前无可用的 MEMORY.md 索引文件。")

    parts.append(format_recall_tool_param_disclosure())
    return parts
