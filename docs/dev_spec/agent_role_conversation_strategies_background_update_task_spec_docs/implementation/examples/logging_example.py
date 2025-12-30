"""
日志记录示例代码

演示如何使用 logfire 和 Langfuse 进行结构化日志记录。
"""

from api.logger.datamodel import LangFuseTraceAttributes, LangFuseSpanAttributes
from api.logger.time import now_iso
import logfire


async def _run_background_update_task(user_id, role_name):
    """执行后台更新任务，包含完整的日志记录"""
    # 创建 trace 级别的元数据
    langfuse_trace_attributes = LangFuseTraceAttributes(
        name="agent-role-update::background_update_task",
        user_id=str(user_id),
        metadata={
            "role_name": role_name,
        }
    )

    with logfire.set_baggage(**langfuse_trace_attributes.model_dump(mode="json", by_alias=True)) as _:
        # 创建 span
        langfuse_observation_attributes = LangFuseSpanAttributes(
            observation_type="span",
        )

        with logfire.span("agent-role-update::task_start",
                          **langfuse_observation_attributes.model_dump(mode="json", by_alias=True)) as span:

            # 第一阶段：计划更新任务
            logfire.info("agent-role-update::phase1_start",
                        user_id=str(user_id),
                        role_name=role_name)

            # ... 执行第一阶段 ...

            logfire.info("agent-role-update::phase1_complete",
                        user_id=str(user_id),
                        role_name=role_name)

            # 第二阶段：准备文件内容
            logfire.info("agent-role-update::phase2_start",
                        user_id=str(user_id),
                        role_name=role_name)

            try:
                # ... 读取文件 ...
                logfire.info("agent-role-update::files_read_success",
                            files_read=["conversation_strategies.md", "concluding_guidance.md", "strategies_update_cache.json"])
            except Exception as e:
                logfire.error("agent-role-update::files_read_failed",
                            error_message=str(e),
                            error_type=type(e).__name__)
                return

            # 第三阶段：更新任务
            logfire.info("agent-role-update::phase3_start",
                        user_id=str(user_id),
                        role_name=role_name)

            # ... Agent 循环执行 ...

            logfire.info("agent-role-update::task_complete",
                        user_id=str(user_id),
                        role_name=role_name)


def logfire_span_example():
    """Span 嵌套示例"""
    with logfire.span("agent-role-update::phase3_update"):
        for loop_count in range(MAX_REVIEW_LOOPS):
            with logfire.span("agent-role-update::agent_loop", loop_count=loop_count):
                # Agent A
                for retry_count in range(MAX_TOOL_CALL_RETRIES):
                    with logfire.span("agent-role-update::agent_a",
                                    retry_count=retry_count) as span:
                        # 执行 Agent A
                        if tool_called:
                            break
                    # 否则重试

                # Agent B
                for retry_count in range(MAX_TOOL_CALL_RETRIES):
                    with logfire.span("agent-role-update::agent_b",
                                    retry_count=retry_count) as span:
                        # 执行 Agent B
                        if tool_called:
                            break

                # Agent C
                with logfire.span("agent-role-update::agent_c"):
                    # 执行 Agent C
                    score, suggestions = ...

                # 检查审查结果
                if score >= 80:
                    logfire.info("agent-role-update::review_passed", score=score)
                    break
                else:
                    logfire.info("agent-role-update::review_failed",
                                score=score, suggestions=suggestions)
