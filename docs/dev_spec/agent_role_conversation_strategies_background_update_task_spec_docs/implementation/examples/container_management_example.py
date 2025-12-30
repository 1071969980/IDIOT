"""
容器管理示例代码

演示如何使用外部容器模式管理 Agent 的执行结果。
"""


async def execute_update_phase(
    user_id: UUID,
    role_name: str,
    original_strategies: str,
    original_guidance: str,
    strategies_update_list: str
) -> None:
    """第三阶段：更新任务（Agent 循环）"""

    # ========== 初始化所有外部容器 ==========
    agent_a_working_strategies = {"value": original_strategies}
    agent_a_result: AgentAResult = {"updated_strategies": "", "tool_called": False}

    agent_b_working_guidance = {"value": original_guidance}
    agent_b_result: AgentBResult = {"updated_guidance": "", "tool_called": False}

    agent_c_result: AgentCResult = {"score": 0, "suggestions": ""}

    # ========== Agent 循环 ==========
    for loop_count in range(MAX_REVIEW_LOOPS):
        # Agent A 执行
        await run_agent_a_update_strategies(
            original_strategies=original_strategies,
            strategies_update_list=strategies_update_list,
            review_suggestions=agent_c_result["suggestions"] if loop_count > 0 else None,
            service_name="default",
            agent_a_working_strategies=agent_a_working_strategies,  # ← 传递工作容器
            agent_a_result=agent_a_result  # ← 传递结果容器
        )

        # 检查 Agent A 是否成功执行
        if not agent_a_result["tool_called"]:
            # 重试逻辑已在 Agent 函数内部处理
            raise RuntimeError("Agent A failed to call edit_strategies tool")

        # 提取 Agent A 的最终结果
        agent_a_result["updated_strategies"] = agent_a_working_strategies["value"]

        # Agent B 执行（使用 Agent A 的结果）
        await run_agent_b_update_guidance(
            updated_strategies=agent_a_result["updated_strategies"],
            original_guidance=original_guidance,
            review_suggestions=agent_c_result["suggestions"] if loop_count > 0 else None,
            service_name="default",
            agent_b_working_guidance=agent_b_working_guidance,
            agent_b_result=agent_b_result
        )

        if not agent_b_result["tool_called"]:
            raise RuntimeError("Agent B failed to call edit_guidance tool")

        # 提取 Agent B 的最终结果
        agent_b_result["updated_guidance"] = agent_b_working_guidance["value"]

        # Agent C 执行（审查结果）
        await run_agent_c_review(
            original_strategies=original_strategies,
            original_guidance=original_guidance,
            updated_strategies=agent_a_result["updated_strategies"],
            updated_guidance=agent_b_result["updated_guidance"],
            service_name="default",
            agent_c_result=agent_c_result
        )

        # 检查审查结果
        if agent_c_result["score"] >= REVIEW_PASS_THRESHOLD:
            # 审查通过，写入文件系统
            await write_files_to_filesystem(
                user_id=user_id,
                role_name=role_name,
                strategies=agent_a_result["updated_strategies"],
                guidance=agent_b_result["updated_guidance"]
            )
            break
        # 否则继续下一轮循环
