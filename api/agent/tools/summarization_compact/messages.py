from typing import Literal

import ujson

from api.agent.xml_marks_def import (SYS_REMINDER_BLOCK_START,
                                     SYS_REMINDER_BLOCK_END,
                                     TOOL_DISCOVERY_RESULT_BLOCK_START,
                                     TOOL_DISCOVERY_RESULT_BLOCK_END,)

from .config_data_model import GENERATION_TOOL_PARAM

# 阈值常量
SUGGEST_COMPACT_THRESHOLD = 80_000
MUST_COMPACT_THRESHOLD = 120_000


def should_compact(input_new_token: int) -> Literal["no", "suggest", "must"]:
    """根据 token 使用量判断压缩级别。"""
    if input_new_token >= MUST_COMPACT_THRESHOLD:
        return "must"
    if input_new_token >= SUGGEST_COMPACT_THRESHOLD:
        return "suggest"
    return "no"


def build_compact_instruction(level: Literal["suggest", "must"]) -> str:
    """构建压缩指令消息。"""
    if level == "suggest":
        return (
            f"{SYS_REMINDER_BLOCK_START}\n"
            "你的对话上下文已接近容量上限。建议你尽快使用 summarization_compact 工具进行上下文压缩，"
            "以避免后续生成被强制中断。\n"
            "你可以先完成当前正在进行的操作，但在开始新的复杂任务前，请务必进行压缩。\n"
            f"{SYS_REMINDER_BLOCK_END}"
        )
    else:  # must
        return (
            f"{SYS_REMINDER_BLOCK_START}\n"
            "你的对话上下文已达到容量上限，必须立即使用 summarization_compact 工具进行上下文压缩。\n"
            "这是强制要求，你必须调用 summarization_compact 工具后才能继续其他操作。\n"
            f"{SYS_REMINDER_BLOCK_END}"
        )


def build_compact_guidance() -> str:
    """构建压缩指导，指导总结内容。"""
    return (
        f"{SYS_REMINDER_BLOCK_START}\n"
        "## 压缩指导\n\n"
        "请在总结中包含以下信息：\n"
        "1. **当前任务状态**：你正在做什么，完成了哪些步骤\n"
        "2. **重要决策和结论**：已经做出的关键判断和决策\n"
        "3. **关键数据**：文件路径、变量名、配置值等重要信息\n"
        "4. **未完成事项**：还需要继续完成的操作\n\n"
        "总结应当简洁但完整，确保基于总结能无缝继续当前任务。\n"
        "不要包含已经过时的中间尝试或错误信息。\n"
        f"{SYS_REMINDER_BLOCK_END}"
    )


def format_tool_param_disclosure() -> str:
    """格式化渲染 GENERATION_TOOL_PARAM 为文本，帮助 LLM 理解工具参数。"""
    func_def = GENERATION_TOOL_PARAM["function"]
    return (
        f"{TOOL_DISCOVERY_RESULT_BLOCK_START}\n"
        f"{ujson.dumps(func_def, ensure_ascii=False)} \n"
        f"{TOOL_DISCOVERY_RESULT_BLOCK_START}\n"
    )
