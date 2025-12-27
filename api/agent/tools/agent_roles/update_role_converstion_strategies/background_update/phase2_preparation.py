"""
第二阶段：准备文件内容

功能：读取所需的用户空间文件内容到内存，并处理缓存文件

执行逻辑：
1. 读取三个文件到内存：
   - conversation_strategies.md → original_strategies
   - concluding_guidance.md → original_guidance
   - strategies_update_cache.json → update_cache
2. 提取 strategies_list 并格式化为易读文本
3. 清空缓存文件的 strategies_update_cache 数组（保留其他 JSON 结构）
4. 如果 strategies_list 为空，返回 None（跳过第三阶段）
5. 返回三个字符串的元组

异常处理：
- 文件不存在或读取失败：记录日志，返回 None（无需回滚）
- 缓存文件清空失败：记录日志，但继续执行（因为已读取到内存）

设计文档参考：
- docs/dev_spec/agent_role_conversation_strategies_background_update_task_spec_docs/background_update_task_spec_design.md#22-agent-循环设计
"""

from uuid import UUID
from typing import Tuple
import logfire
import ujson

from api.agent.tools.agent_roles.utils import (
    user_agent_role_conversation_strategies_file,
    user_agent_role_concluding_guidence_file,
    user_agent_role_strategies_update_cache_file,
)
from api.user_space.file_system.fs_utils.exception import (
    HybridFileNotFoundError,
    LockAcquisitionError,
    S3OperationError,
    DatabaseOperationError,
)


async def execute_preparation_phase(
    user_id: UUID,
    role_name: str
) -> Tuple[str, str, str] | None:
    """
    执行第二阶段：准备文件内容

    读取三个文件到内存，提取并格式化更新请求，清空缓存文件。

    参数:
        user_id: 用户 ID
        role_name: 角色名称

    返回:
        成功：返回 (original_strategies, original_guidance, strategies_update_list) 元组
        失败或无更新：返回 None
    """
    logfire.info(
        "agent-role-update::phase2_start",
        user_id=str(user_id),
        role_name=role_name
    )

    try:
        # ========== 步骤1: 读取缓存文件 ==========
        async with user_agent_role_strategies_update_cache_file(user_id, role_name, "r") as f:
            cache_content = f.read().decode("utf-8")
            update_cache = ujson.loads(cache_content) if cache_content else {}

        # ========== 步骤2: 提取更新列表 ==========
        strategies_list = update_cache.get("strategies_update_cache", [])

        # 检查退出条件：如果列表为空，没有待处理的更新
        if not strategies_list:
            logfire.info(
                "agent-role-update::no_updates_pending",
                user_id=str(user_id),
                role_name=role_name
            )
            return None

        # ========== 步骤3: 格式化 strategies_list 为易读文本 ==========
        formatted_items = []
        for i, item in enumerate(strategies_list, 1):
            formatted_items.append(
                f"## 更新请求 {i}\n\n"
                f"**更新内容**:\n{item['update_content']}\n\n"
                f"**相关上下文**:\n{item['context']}"
            )
        strategies_update_list = "\n\n".join(formatted_items)

        logfire.info(
            "agent-role-update::cache_updates_extracted",
            user_id=str(user_id),
            role_name=role_name,
            update_count=len(strategies_list)
        )

        # ========== 步骤4: 清空缓存文件的 strategies_update_cache 数组 ==========
        update_cache["strategies_update_cache"] = []
        async with user_agent_role_strategies_update_cache_file(user_id, role_name, "w") as f:
            f.write(ujson.dumps(update_cache).encode("utf-8"))

        logfire.info(
            "agent-role-update::cache_cleared",
            user_id=str(user_id),
            role_name=role_name
        )

        # ========== 步骤5: 读取对话策略文件 ==========
        async with user_agent_role_conversation_strategies_file(user_id, role_name, "r") as f:
            original_strategies = f.read().decode("utf-8")

        # ========== 步骤6: 读取对话总结指导文件 ==========
        async with user_agent_role_concluding_guidence_file(user_id, role_name, "r") as f:
            original_guidance = f.read().decode("utf-8")

        logfire.info(
            "agent-role-update::files_read_success",
            user_id=str(user_id),
            role_name=role_name,
            files_read=["conversation_strategies.md", "concluding_guidance.md", "strategies_update_cache.json"]
        )

        logfire.info(
            "agent-role-update::phase2_complete",
            user_id=str(user_id),
            role_name=role_name
        )

        return (original_strategies, original_guidance, strategies_update_list)

    except HybridFileNotFoundError as e:
        logfire.error(
            "agent-role-update::file_not_found",
            user_id=str(user_id),
            role_name=role_name,
            error_type="HybridFileNotFoundError",
            error_message=str(e)
        )
        return None

    except LockAcquisitionError as e:
        logfire.error(
            "agent-role-update::lock_acquisition_failed",
            user_id=str(user_id),
            role_name=role_name,
            error_type="LockAcquisitionError",
            error_message=str(e)
        )
        return None

    except (S3OperationError, DatabaseOperationError) as e:
        logfire.error(
            "agent-role-update::file_operation_failed",
            user_id=str(user_id),
            role_name=role_name,
            error_type=type(e).__name__,
            error_message=str(e)
        )
        return None

    except Exception as e:
        logfire.error(
            "agent-role-update::unexpected_read_error",
            user_id=str(user_id),
            role_name=role_name,
            error_type=type(e).__name__,
            error_message=str(e)
        )
        return None
