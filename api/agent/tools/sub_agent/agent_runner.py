# api/agent/tools/sub_agent/agent_runner.py

"""子 agent 执行器。"""

import asyncio
from uuid import UUID

import logfire
from openai.types.chat.chat_completion_user_message_param import ChatCompletionUserMessageParam

from api.agent.base_agent import AgentBase
from api.agent.session_agent_config.config_data_model import (
    AVILABLE_TOOLS_CONFIG_FOR_SUB_AGENT,
    CURRENT_VERSION,
    SessionAgentConfig,
)
from api.agent.sql_stat.u2a_session_agent_config.utils import (
    update_session_config_by_session_id,
)
from api.agent.sql_stat.u2a_session_storage.utils import (
    get_session_storage_by_session_id,
    u2a_session_storage_lock,
    update_session_storage_by_session_id,
)
from api.chat.sql_stat.u2a_session.utils import _U2ASessionCreate, insert_session
from api.chat.sql_stat.u2a_session_task.utils import (
    _U2ASessionTaskCreate,
    insert_task,
)
from api.chat.sql_stat.u2a_user_msg.utils import (
    _U2AUserMessageCreate,
    get_next_user_message_seq_index,
    get_user_message_by_id,
    insert_user_message,
)
from api.load_balance.constant import DEEPSEEK_CHAT_SERVICE_NAME

from .definition_loader import SubAgentDefinition
from .submit_result_constructor import ResultContainer, construct_submit_result_tool
from .utils import generate_session_alias


class SubAgentRunner:
    """子 agent 执行器。"""

    def __init__(
        self,
        user_id: UUID,
        parent_session_id: UUID,
        agent_definition: SubAgentDefinition,
        task: str,
        session_alias: str | None,
        cancel_event: asyncio.Event | None,
    ):
        """初始化子 agent 执行器。

        Args:
            user_id: 用户 ID
            parent_session_id: 主 agent 的会话 ID
            agent_definition: 子 agent 定义
            task: 任务描述
            session_alias: 会话别名（用于复用）
        """
        self.user_id = user_id
        self.parent_session_id = parent_session_id
        self.agent_definition = agent_definition
        self.task = task
        self.session_alias = session_alias
        self.result_container: ResultContainer | None = None
        self.cancel_event = cancel_event

    async def _create_new_session(self) -> UUID:
        """创建新的子 agent 会话。

        Returns:
            新创建的会话 ID
        """
        # 创建会话
        session_data = _U2ASessionCreate(
            user_id=self.user_id,
            title=f"Sub-agent: {self.agent_definition.name}",
            created_by="agent"
        )
        sub_session_id = await insert_session(session_data)

        # 存储映射到 session_storage
        async with u2a_session_storage_lock(self.parent_session_id):
            parent_storage = await get_session_storage_by_session_id(self.parent_session_id)
            new_storage_dict = {}
            if parent_storage is not None:
                new_storage_dict = parent_storage.storage
            
            if "sub_agent_session" not in new_storage_dict:
                new_storage_dict["sub_agent_session"] = {}

            while True:
                self.session_alias = generate_session_alias()
                if self.session_alias not in new_storage_dict["sub_agent_session"]:
                    new_storage_dict["sub_agent_session"][self.session_alias] = str(sub_session_id)
                    break
                
            await update_session_storage_by_session_id(self.parent_session_id, new_storage_dict)

        return sub_session_id

    async def _resolve_session_alias(self) -> UUID:
        """解析会话别名，返回子 session_id。

        Returns:
            解析出的子会话 ID

        Raises:
            ValueError: 如果别名无效
        """
        async with u2a_session_storage_lock(self.parent_session_id):
            parent_storage = await get_session_storage_by_session_id(self.parent_session_id)
            if parent_storage is None:
                raise ValueError(f"无效的会话别名：{self.session_alias}")
            
            parent_storage_dict = parent_storage.storage

            if "sub_agent_session" not in parent_storage_dict:
                raise ValueError(f"无效的会话别名：{self.session_alias}")

            sub_session_id_str = parent_storage_dict["sub_agent_session"].get(self.session_alias)
            if not sub_session_id_str:
                raise ValueError(f"无效的会话别名：{self.session_alias}")

            return UUID(sub_session_id_str)

    async def run(self) -> str:
        """执行子 agent 并返回结果。

        Returns:
            子 agent 的执行结果（包含会话别名）
        """
        from api.chat.chat_task import init_tools, session_chat_task
        
        # 1. 创建或复用会话
        if self.session_alias:
            try:
                sub_session_id = await self._resolve_session_alias()
            except ValueError:
                sub_session_id = await self._create_new_session()
        else:
            sub_session_id = await self._create_new_session()

        # 2. 创建 session_task
        task_data = _U2ASessionTaskCreate(
            session_id=sub_session_id,
            user_id=self.user_id,
            status="pending"
        )
        sub_task_id = await insert_task(task_data)

        # 3. 添加用户消息
        seq_index = await get_next_user_message_seq_index(sub_session_id)
        user_message_create = _U2AUserMessageCreate(
            user_id=self.user_id,
            session_id=sub_session_id,
            seq_index=seq_index,
            message_type="text",
            content=self.task,
            status="agent_working_for_user",
            session_task_id=sub_task_id,
        )
        user_message_id = await insert_user_message(user_message_create)
        user_message = await get_user_message_by_id(user_message_id)
        if user_message is None:
            return "子 agent 执行时发生错误：构造消息失败。请不要再尝试指名调用该子 Agent。"
        
        # 4. 创建结果容器和工具
        self.result_container = ResultContainer()
        submit_result_param, submit_result_closure = construct_submit_result_tool(self.result_container)

        # 5. 构造工具
        tools = [submit_result_param]
        tool_closures = {"submit_result": submit_result_closure}

        # 构造内建工具
        
        if self.agent_definition.tools:
            
            ## 设置 SessionAgentConfig
            session_agent_tool_config = {}
            for tool_name in self.agent_definition.tools:
                if tool_name in AVILABLE_TOOLS_CONFIG_FOR_SUB_AGENT:
                    session_agent_tool_config[tool_name] = AVILABLE_TOOLS_CONFIG_FOR_SUB_AGENT[tool_name]
                else:
                    return f"子 agent 执行时发生错误：子 agent 定义有误，{tool_name} 工具不被允许或不存在。请不要再尝试指名调用该子 Agent。"
                
            await update_session_config_by_session_id(
                sub_session_id,
                SessionAgentConfig(
                    version=CURRENT_VERSION,
                    tools_config=session_agent_tool_config
                ).model_dump(mode="json")
            )
            
            ## 初始化工具
            build_in_tools, build_in_tool_closures = await init_tools(
                user_id=self.user_id,
                session_id=sub_session_id,
                session_task_id=sub_task_id
            )
            
            tools.extend(build_in_tools)
            tool_closures.update(build_in_tool_closures)
        
        agent_exception = await session_chat_task(
            user_id=self.user_id,
            session_id=sub_session_id,
            session_task_id=sub_task_id,
            llm_service=DEEPSEEK_CHAT_SERVICE_NAME,
            system_prompt=self.agent_definition.system_prompt,
            pending_messages=[user_message],
            during_processing_tasks=[],
            tools=tools,
            tool_call_function=tool_closures,
            cancel_event=self.cancel_event
        )
        
        if agent_exception is not None:
            logfire.error(f"子 agent 执行异常: {agent_exception}")
            return f"子 agent 执行时发生未知错误。请不要再尝试指名调用该子 Agent。"

        # 8. 处理结果
        if self.result_container.called:
            result = self.result_container.result
        else:
            result = f"子 agent 已完成任务但未返回结果。请重新调用 sub_agent 工具，使用会话别名 {self.session_alias}，重入会话，要求子 agent 调用 submit_result 返回结果。"

        return f"{result}\n\n[会话别名: {self.session_alias}]"
