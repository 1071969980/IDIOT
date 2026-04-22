from typing import Any


async def build_skill_message(
    skills: list[str],
    caller_snapshot: dict[str, Any],
) -> str | None:
    """构建 skills 管理指令消息。

    对比 agent 定义中要求的 skills 和当前已加载的 skills，
    生成加载/卸载指令。

    Args:
        skills: agent 定义中要求加载的技能列表
        caller_snapshot: 调用方分支的 storage_snapshot

    Returns:
        构建的指令消息文本，如果 skills 为空列表则返回 None
    """
    if not skills:
        return None

    loaded_skills: list[str] = caller_snapshot.get("loaded_skills", [])

    to_load = [s for s in skills if s not in loaded_skills]
    to_unload = [s for s in loaded_skills if s not in skills]

    if not to_load and not to_unload:
        return None

    parts: list[str] = []

    if to_load:
        parts.append("请加载以下技能（使用 load_skill 工具）：\n" + "\n".join(f"- {s}" for s in to_load))

    if to_unload:
        parts.append(
            "\n以下已加载技能不在本次任务所需列表，请卸载（使用 unload_skill 工具）：\n"
            + "\n".join(f"- {s}" for s in to_unload)
        )

    return "".join(parts)


def build_feedback_message(branch_name: str) -> str:
    """构建反馈说明消息。

    Returns:
        固定的反馈说明文本
    """
    return (
        f'完成任务后，或者需要调用分支协助时，你需要向调用分支反馈执行结果。为此需要使用 feed_message 工具向 `{branch_name}` 分支发送反馈消息\n\n'
    )
