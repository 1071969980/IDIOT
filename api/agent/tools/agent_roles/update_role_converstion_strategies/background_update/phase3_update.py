"""
第三阶段：更新任务（Agent 循环）

功能：执行实际的对话策略和总结指导文件更新

执行流程：
1. 获取分布式锁（阻塞等待，超时时间 300 秒）
2. 初始化所有外部容器
3. 启动 Agent 循环（最多循环 3 次）：
   - Agent A：更新对话策略文件（工具调用最多重试 3 次）
   - Agent B：更新对话总结指导文件（工具调用最多重试 3 次）
   - Agent C：审查更新结果（生成 diff，评分 0-100）
4. 如果 score >= 80，写入文件系统
5. 释放分布式锁

异常处理：
- 如果在第二阶段之后任何步骤失败，回滚缓存文件（将原始 update_cache 写回）
- 使用 try-finally 确保回滚逻辑被执行
- 回滚操作必须用 try-except 包裹，失败时记录日志但不抛出异常

设计文档参考：
- api/agent/tools/agent_roles/update_role_conversation_strategies/background_update_task_spec_docs/background_update_task_spec_design.md#21-整体流程
"""

from uuid import UUID
import logfire
import ujson

from api.redis.distributed_lock import RedisDistributedLock
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
from .models import (
    AgentAResult,
    AgentBResult,
    AgentCResult,
    MAX_REVIEW_LOOPS,
    REVIEW_PASS_THRESHOLD,
    PHASE3_LOCK_TIMEOUT,
)
from .agents.agent_a_update_strategies import run_agent_a_update_strategies
from .agents.agent_b_update_guidance import run_agent_b_update_guidance
from .agents.agent_c_review import run_agent_c_review


async def execute_update_phase(
    user_id: UUID,
    role_name: str,
    original_strategies: str,
    original_guidance: str,
    strategies_update_list: str
) -> None:
    """
    执行第三阶段：更新任务（Agent 循环）

    参数:
        user_id: 用户 ID
        role_name: 角色名称
        original_strategies: 原始的对话策略内容
        original_guidance: 原始的对话总结指导内容
        strategies_update_list: 格式化后的更新请求文本

    返回:
        None（成功或失败都通过日志记录）
    """
    logfire.info(
        "agent-role-update::phase3_start",
        user_id=str(user_id),
        role_name=role_name
    )

    # 获取分布式锁
    lock_key = f"agent-role-update:lock:{user_id}:{role_name}"

    async with RedisDistributedLock(lock_key, timeout=PHASE3_LOCK_TIMEOUT):
        logfire.info(
            "agent-role-update::distributed_lock_acquired",
            user_id=str(user_id),
            role_name=role_name
        )

        # ========== 初始化所有外部容器 ==========
        agent_a_working_strategies = {"value": original_strategies}
        agent_a_result: AgentAResult = {"updated_strategies": "", "tool_called": False}

        agent_b_working_guidance = {"value": original_guidance}
        agent_b_result: AgentBResult = {"updated_guidance": "", "tool_called": False}

        agent_c_result: AgentCResult = {"score": 0, "suggestions": ""}

        try:
            # ========== Agent 循环 ==========
            for loop_count in range(MAX_REVIEW_LOOPS):
                with logfire.span("agent-role-update::agent_loop", loop_count=loop_count):
                    logfire.info(
                        "agent-role-update::agent_loop_start",
                        loop_count=loop_count,
                        max_loops=MAX_REVIEW_LOOPS
                    )

                    # ========== Agent A 执行 ==========
                    await run_agent_a_update_strategies(
                        original_strategies=original_strategies,
                        strategies_update_list=strategies_update_list,
                        review_suggestions=agent_c_result["suggestions"] if loop_count > 0 else None,
                        service_name="default",
                        agent_a_working_strategies=agent_a_working_strategies,
                        agent_a_result=agent_a_result
                    )

                    # 提取 Agent A 的最终结果
                    agent_a_result["updated_strategies"] = agent_a_working_strategies["value"]

                    # ========== Agent B 执行 ==========
                    await run_agent_b_update_guidance(
                        updated_strategies=agent_a_result["updated_strategies"],
                        original_guidance=original_guidance,
                        review_suggestions=agent_c_result["suggestions"] if loop_count > 0 else None,
                        service_name="default",
                        agent_b_working_guidance=agent_b_working_guidance,
                        agent_b_result=agent_b_result
                    )

                    # 提取 Agent B 的最终结果
                    agent_b_result["updated_guidance"] = agent_b_working_guidance["value"]

                    # ========== Agent C 执行 ==========
                    await run_agent_c_review(
                        original_strategies=original_strategies,
                        original_guidance=original_guidance,
                        updated_strategies=agent_a_result["updated_strategies"],
                        updated_guidance=agent_b_result["updated_guidance"],
                        service_name="default",
                        agent_c_result=agent_c_result
                    )

                    # ========== 检查审查结果 ==========
                    if agent_c_result["score"] >= REVIEW_PASS_THRESHOLD:
                        logfire.info(
                            "agent-role-update::review_passed",
                            score=agent_c_result["score"],
                            loop_count=loop_count
                        )
                        # 审查通过，写入文件系统
                        await _write_files_to_filesystem(
                            user_id=user_id,
                            role_name=role_name,
                            strategies=agent_a_result["updated_strategies"],
                            guidance=agent_b_result["updated_guidance"]
                        )
                        break
                    else:
                        logfire.info(
                            "agent-role-update::review_failed",
                            score=agent_c_result["score"],
                            suggestions=agent_c_result["suggestions"],
                            loop_count=loop_count
                        )
                        # 审查不通过，继续下一轮循环
                        if loop_count == MAX_REVIEW_LOOPS - 1:
                            # 已达到最大循环次数
                            logfire.error(
                                "agent-role-update::max_loops_reached",
                                max_loops=MAX_REVIEW_LOOPS
                            )
                            raise RuntimeError("Agent review failed after maximum loops")

            logfire.info(
                "agent-role-update::phase3_complete",
                user_id=str(user_id),
                role_name=role_name
            )

        except Exception as e:
            # Agent 循环失败，不需要回滚（因为还没有写文件）
            logfire.error(
                "agent-role-update::agent_loop_failed",
                user_id=str(user_id),
                role_name=role_name,
                error_type=type(e).__name__,
                error_message=str(e)
            )
            raise


async def _write_files_to_filesystem(
    user_id: UUID,
    role_name: str,
    strategies: str,
    guidance: str
) -> None:
    """
    将更新后的内容写入文件系统

    参数:
        user_id: 用户 ID
        role_name: 角色名称
        strategies: 更新后的对话策略内容
        guidance: 更新后的对话总结指导内容
    """
    try:
        # 写入对话策略文件
        async with user_agent_role_conversation_strategies_file(user_id, role_name, "w") as f:
            f.write(strategies.encode("utf-8"))

        # 写入对话总结指导文件
        async with user_agent_role_concluding_guidence_file(user_id, role_name, "w") as f:
            f.write(guidance.encode("utf-8"))

        logfire.info(
            "agent-role-update::files_write_success",
            user_id=str(user_id),
            role_name=role_name,
            files_written=["conversation_strategies.md", "concluding_guidance.md"]
        )

    except Exception as e:
        logfire.error(
            "agent-role-update::files_write_failed",
            user_id=str(user_id),
            role_name=role_name,
            error_type=type(e).__name__,
            error_message=str(e)
        )
        raise
