# api/agent/tools/skills/skill_advisor/advisor_runner.py

"""skill_advisor 的 sub-agent 执行器。"""

import asyncio
from uuid import UUID

from api.agent.sql_stat.u2a_session_agent_config.utils import update_session_config_by_session_id
from api.chat.sql_stat.u2a_session.utils import _U2ASessionCreate, insert_session
from api.chat.sql_stat.u2a_session_branch_task.operations import create_root_task_with_branch
from api.chat.sql_stat.u2a_user_msg.utils import (
    _U2AUserMessageCreate,
    get_next_user_message_seq_index,
    get_user_message_by_id,
    insert_user_message,
)
from api.load_balance.constant import DEEPSEEK_CHAT_SERVICE_NAME

from api.agent.tools.skills.data_model import SkillInfo, SkillAdvisorResult
from .submit_result_constructor import (
    SkillAdvisorResultContainer,
    construct_submit_result_tool,
)


SKILL_ADVISOR_SYSTEM_PROMPT = """你是一个技能顾问。你的任务是分析用户的问题并推荐最相关的技能。

可用技能列表：
{skill_list}

你的任务：
1. 分析用户的问题描述
2. 从上面的列表中识别最相关的技能
3. 使用 submit_result 工具返回推荐结果

submit_result 工具参数说明：
- recommendations: 推荐的技能列表，每个元素包含：
  - skill_name: 技能显示名
  - skill_path: 技能目录路径
  - relevance_reason: 相关性理由
- analysis: 问题分析和技能匹配的简要分析

重要提示：
- 只推荐真正相关的技能
- 最多推荐 5 个技能
- 如果没有相关技能，返回空的 recommendations 列表
- 必须调用 submit_result 返回最终答案
"""


class SkillAdvisorRunner:
    """skill_advisor 的 sub-agent 执行器。"""

    def __init__(
        self,
        user_id: UUID,
        parent_session_id: UUID,
        prompt: str,
        skill_infos: dict[str, SkillInfo],
        cancel_event: asyncio.Event | None = None,
    ):
        self.user_id = user_id
        self.parent_session_id = parent_session_id
        self.prompt = prompt
        self.skill_infos = skill_infos
        self.cancel_event = cancel_event
        self.result_container: SkillAdvisorResultContainer | None = None

    async def run(self) -> SkillAdvisorResult:
        """执行技能推荐并返回结构化结果。

        Raises:
            RuntimeError: 会话创建失败或 sub-agent 未返回结果
        """
        from api.chat.chat_task import init_tools, session_chat_task
        from api.agent.session_agent_config.config_data_model import (
            AVILABLE_TOOLS_CONFIG_FOR_SUB_AGENT,
            SessionAgentConfig,
        )
        from api.agent.tools.tool_factory import UserToolCallingPermissionRole

        # 1. 创建 sub-agent 会话（system type, archived）
        session_data = _U2ASessionCreate(
            user_id=self.user_id,
            title="Skill Advisor Session",
            created_by="system",
            archived=True,
            created_from_id_by_agent=self.parent_session_id
        )
        sub_session_id = await insert_session(session_data)

        # 2. 创建 session task（含默认 main branch）
        _, sub_task_id = await create_root_task_with_branch(
            session_id=sub_session_id,
            user_id=self.user_id,
            name="main",
            created_by="system",
        )

        # 3. 添加用户消息
        seq_index = await get_next_user_message_seq_index(sub_session_id)
        user_message_create = _U2AUserMessageCreate(
            user_id=self.user_id,
            session_id=sub_session_id,
            seq_index=seq_index,
            message_type="text",
            content=self.prompt,
            status="agent_working_for_user",
            session_task_id=sub_task_id,
        )
        user_message_id = await insert_user_message(user_message_create)
        user_message = await get_user_message_by_id(user_message_id)

        if user_message is None:
            raise RuntimeError("技能顾问会话创建失败：无法获取用户消息")

        # 4. 构建系统提示词
        skill_list = "\n".join([
            f"- {info.name}: {info.description} (路径: {info.path})"
            for info in self.skill_infos.values()
        ])
        system_prompt = SKILL_ADVISOR_SYSTEM_PROMPT.format(skill_list=skill_list)

        # 5. 创建结果容器和动态工具
        self.result_container = SkillAdvisorResultContainer()
        submit_result_param, submit_result_closure = construct_submit_result_tool(
            self.result_container
        )

        tools = [submit_result_param]
        tool_closures = {"submit_result": submit_result_closure}

        # 6. 初始化只读文件工具
        read_only_tool_names = ["read_file", "list_directory"]
        read_only_config = {}
        for name in read_only_tool_names:
            if name in AVILABLE_TOOLS_CONFIG_FOR_SUB_AGENT:
                read_only_config[name] = AVILABLE_TOOLS_CONFIG_FOR_SUB_AGENT[name]

        if read_only_config:
            await update_session_config_by_session_id(
                sub_session_id,
                SessionAgentConfig(tools_config=read_only_config).model_dump(mode="json")
            )

            built_in_tools, built_in_closures = await init_tools(
                user_id_for_scope=self.user_id,
                session_id=sub_session_id,
                session_task_id=sub_task_id,
                user_permission_role=UserToolCallingPermissionRole.OWNER
            )
            tools.extend(built_in_tools)
            tool_closures.update(built_in_closures)

        # 7. 运行 sub-agent
        await session_chat_task(
            user_id=self.user_id,
            session_id=sub_session_id,
            session_task_id=sub_task_id,
            llm_service=DEEPSEEK_CHAT_SERVICE_NAME,
            system_prompt=system_prompt,
            pending_messages=[user_message],
            during_processing_tasks=[],
            tools=tools,
            tool_call_function=tool_closures,
            cancel_event=self.cancel_event
        )

        # 8. 处理结果
        if self.result_container.called:
            return SkillAdvisorResult(
                recommendations=self.result_container.result or [],
                analysis=self.result_container.analysis or ""
            )
        else:
            raise RuntimeError("技能顾问完成但未返回推荐结果")