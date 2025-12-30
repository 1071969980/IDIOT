"""
错误处理代码模式示例

演示如何在后台更新任务中处理各种异常情况，
包括文件读取失败、写入失败以及回滚操作。
"""

from api.user_space.file_system.fs_utils.exception import (
    HybridFileNotFoundError,
    LockAcquisitionError,
    S3OperationError,
    DatabaseOperationError,
)
from api.agent.tools.agent_roles.utils import (
    user_agent_role_conversation_strategies_file,
    user_agent_role_concluding_guidence_file,  # 注意拼写：guidence
    user_agent_role_strategies_update_cache_file,
)


async def run_background_update_task(user_id: UUID, role_name: str):
    """执行后台更新任务的入口函数"""
    original_update_cache = None  # 用于跟踪原始缓存内容
    cache_modified = False  # 用于跟踪缓存是否已被修改

    try:
        # 第二阶段：准备文件内容
        try:
            # ========== 在同一个分布式锁内完成缓存文件的读取、提取、格式化、清空 ==========
            async with user_agent_role_strategies_update_cache_file(user_id, role_name, "r+") as f:
                cache_content = f.read().decode("utf-8")
                update_cache = ujson.loads(cache_content) if cache_content else {}
                original_update_cache = update_cache.copy()  # 保存原始内容

                # 提取更新列表
                strategies_list = update_cache.get("strategies_update_cache", [])

                # 检查退出条件
                if not strategies_list:
                    logfire.info("agent-role-update::no_updates_pending")
                    return  # 没有待处理的更新，正常结束

                # ========== 关键步骤：格式化 strategies_list 为易读文本 ==========
                # 将 strategies_list 数组格式化为 Markdown 格式的文本
                # 以便传递给 Agent A 的 prompt.compile() 方法
                # 注意：格式化操作在锁内完成，但操作很快，不会长时间持有锁
                formatted_items = []
                for i, item in enumerate(strategies_list, 1):
                    formatted_items.append(
                        f"## 更新请求 {i}\n\n"
                        f"**更新内容**:\n{item['update_content']}\n\n"
                        f"**相关上下文**:\n{item['context']}"
                    )
                strategies_update_list = "\n\n".join(formatted_items)
                # ========== 格式化结束 ==========

                # 清空 strategies_update_cache 数组（保留其他 JSON 结构）
                update_cache["strategies_update_cache"] = []

                # 将更新后的缓存写回文件（在同一锁内，确保原子性）
                f.seek(0)  # 回到文件开头
                f.write(ujson.dumps(update_cache).encode("utf-8"))
                f.truncate()  # 截断文件，移除旧内容
                cache_modified = True

            # 读取其他文件（独立操作，不在缓存文件的锁内）
            async with user_agent_role_conversation_strategies_file(user_id, role_name, "r") as f:
                original_strategies = f.read().decode("utf-8")

            async with user_agent_role_concluding_guidence_file(user_id, role_name, "r") as f:
                original_guidance = f.read().decode("utf-8")

            # 调用第三阶段
            await execute_update_phase(
                user_id=user_id,
                role_name=role_name,
                original_strategies=original_strategies,
                original_guidance=original_guidance,
                strategies_update_list=strategies_update_list  # 传入格式化后的文本
            )

        except HybridFileNotFoundError as e:
            logfire.error("agent-role-update::file_not_found",
                         file_path=str(e.file_path) if hasattr(e, 'file_path') else "unknown",
                         error_type="HybridFileNotFoundError",
                         error_message=str(e))
            return  # 文件不存在，缓存未被修改，无需回滚

        except LockAcquisitionError as e:
            logfire.error("agent-role-update::lock_acquisition_failed",
                         error_type="LockAcquisitionError",
                         error_message=str(e))
            return  # 无法获取锁，缓存未被修改，无需回滚

        except (S3OperationError, DatabaseOperationError) as e:
            logfire.error("agent-role-update::file_operation_failed",
                         error_type=type(e).__name__,
                         error_message=str(e))
            return  # 文件操作失败，缓存未被修改或读取未完成，无需回滚

        except Exception as e:
            logfire.error("agent-role-update::unexpected_read_error",
                         error_type=type(e).__name__,
                         error_message=str(e))
            return  # 其他异常，保守处理，无需回滚

        # 注意：第三阶段的异常处理和回滚逻辑在 `phase3_update.py` 中实现
        # 这里通过调用 `execute_update_phase()` 函数已经处理了所有异常

    except Exception as e:
        # 最外层异常捕获（理论上不应该到达这里）
        logfire.error("agent-role-update::unexpected_error",
                     error_type=type(e).__name__,
                     error_message=str(e))
        return
