# api/agent/tools/sub_agent/agent_runner.py

"""子 agent 执行器 — 支持 standalone 和 fork 两种上下文模式。"""

import asyncio
import logfire
from typing import Any
from uuid import UUID

from api.agent.logic_mark_def import (
    TO_REMINDER_MCP_SERVER_CONFIG_CHANGED_MARK_NAME,
    TO_REMINDER_TOOL_ENABLE_STATUS_MARK_NAME,
)
from api.agent.session_agent_config.constants import (
    SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT,
)
from api.agent.xml_marks_def import EXTERNAL_MESSAGE_BLOCK_END, EXTERNAL_MESSAGE_BLOCK_START, SUB_AGENT_DEF_BLOCK_START, SUB_AGENT_DEF_BLOCK_END, SYS_REMINDER_BLOCK_END, SYS_REMINDER_BLOCK_START
from api.agent.session_agent_config.crud import get_base_session_config, update_config_overlay
from api.agent.tools.data_model import ToolTaskResult
from api.user_pod_command import pod_command_session, execute_command, UserPodCommandError
from api.chat.schedule_pending_task import schedule_pending_task
from api.chat.sql_stat.u2a_session_branch_task.operations import (
    get_or_create_pending_task,
    construct_branch_name,
    create_root_task_with_branch,
    fork_branch,
)
from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_op import (
    get_branch_storage_snapshot,
    update_branch_storage_snapshot,
)
from api.chat.sql_stat.u2a_session_task.utils import (
    get_nearest_ancestor_storage_snapshot,
    get_task,
    update_task_logic_mark_field,
    update_task_storage_snapshot,
)
from api.chat.sql_stat.u2a_user_msg.utils import (
    _U2AUserMessageCreate,
    insert_user_message,
    insert_user_messages_from_list,
)
from api.app.chat.process_pending_messages import _process_pending_messages
from api.redis.event_names import EventNames
from api.redis.redis_event import RedisEvent

from .definition_loader import SubAgentDefinition
from .message_builder import build_feedback_message, build_skill_message
from .utils import generate_session_alias


# ---
# SubAgentRunner
# ---

class SubAgentRunner:
    """子 agent 执行器。"""

    def __init__(
        self,
        agent_def: SubAgentDefinition,
        user_id: UUID,
        session_id: UUID,
        branch_name: str,
        session_task_id: UUID,
        llm_service_name: str,
        cancel_event: asyncio.Event | None = None,
    ):
        self.agent_def = agent_def
        self.user_id = user_id
        self.session_id = session_id
        self.branch_name = branch_name
        self.session_task_id = session_task_id
        self.llm_service_name = llm_service_name
        self.cancel_event = cancel_event

    # ---
    # 公开入口
    # ---

    async def run(
        self,
        task: str,
        context_mode: str,
        should_feedback: bool,
    ) -> ToolTaskResult:
        """根据 context_mode 分发执行。"""
        if context_mode == "fork":
            return await self._run_fork(task, should_feedback)
        return await self._run_standalone(task, should_feedback)

    # ---
    # standalone 模式
    # ---

    async def _run_standalone(self, task: str, should_feedback: bool) -> ToolTaskResult:
        """在独立分支中启动子代理。"""
        # 1. 构建分支名
        sub_branch_name = construct_branch_name(f"__sub_agent_{self.agent_def.name}")

        # 2. 创建 root task + branch
        _branch_id, root_task_id = await create_root_task_with_branch(
            session_id=self.session_id,
            user_id=self.user_id,
            name=sub_branch_name,
            created_by="agent",
        )

        alias = ""

        def _register_sub_agent_session(snapshot: dict, branch_name: str) -> bool:
            """在 storage_snapshot 中注册子代理分支映射（就地修改）。"""
            sessions = snapshot.setdefault("sub_agent_aliases", {})
            while True:
                alias = generate_session_alias()
                if alias in sessions:
                    continue
                sessions[alias] = branch_name
                break
            return True

        # 3. 生成 alias 并写入调用方的 storage_snapshot
        await update_branch_storage_snapshot(
            session_id=self.session_id,
            user_id=self.user_id,
            branch_name=self.branch_name,
            update_fn=lambda snap: _register_sub_agent_session(snap, sub_branch_name),
        )

        # 4. 构建配置覆写并写入 root task
        overlay = await self._build_config_overlay(should_feedback)
        root_task = await get_task(root_task_id)
        await update_config_overlay(
            root_task_id,
            dict(root_task.storage_snapshot) if root_task and root_task.storage_snapshot else {},
            overlay,
        )

        # 5. 设置 logic marks
        await self._set_logic_marks(root_task_id)

        # 6. 构建并批量插入消息
        contents = await self._build_messages(task, should_feedback)

        messages = [
            _U2AUserMessageCreate(
                user_id=self.user_id,
                session_id=self.session_id,
                message_type="text",
                content=msg_content,
                created_by="sub_agent_task",
                status="waiting_agent_ack_user",
                session_task_id=root_task_id,
                process_priority=20,
            )
            for msg_content in contents
        ]

        await insert_user_messages_from_list(messages)

        # 7. 异步启动处理
        service_name = self._resolve_service_name()
        asyncio.create_task(  # noqa: RUF006
            _process_pending_messages(
                user_id=self.user_id,
                session_id=self.session_id,
                branch_name=sub_branch_name,
                llm_service_name=service_name,
            )
        )

        if not self.agent_def.disable_completion_callback:
            asyncio.create_task(  # noqa: RUF006
                self._completed_callback(root_task_id, sub_branch_name, alias, should_feedback)
            )

        return ToolTaskResult(
            str_content=f"子代理 `{self.agent_def.name}` 已在独立上下文中启动，分支名: `{sub_branch_name}`. 别名：`{alias}`。请耐心等待结果。",
            json_content={"branch_name": sub_branch_name, "alias": alias},
            occur_error=False,
        )

    # ---
    # fork 模式
    # ---

    async def _run_fork(self, task: str, should_feedback: bool) -> ToolTaskResult:
        """从当前 task fork 出新分支，继承调用方上下文。"""
        # 1. 构建分支名
        fork_branch_name = construct_branch_name(f"__sub_agent_{self.agent_def.name}")

        # 2. fork
        _branch_id, forked_task_id = await fork_branch(
            session_id=self.session_id,
            name=fork_branch_name,
            created_by="agent",
            parent_task_id=self.session_task_id,
            user_id=self.user_id,
        )

        alias = ""

        def _register_sub_agent_session(snapshot: dict, branch_name: str) -> bool:
            """在 storage_snapshot 中注册子代理分支映射（就地修改）。"""
            sessions = snapshot.setdefault("sub_agent_aliases", {})
            while True:
                alias = generate_session_alias()
                if alias in sessions:
                    continue
                sessions[alias] = branch_name
                break
            return True

        # 3. 生成 alias 并写入调用方的 storage_snapshot
        await update_branch_storage_snapshot(
            session_id=self.session_id,
            user_id=self.user_id,
            branch_name=self.branch_name,
            update_fn=lambda snap: _register_sub_agent_session(snap, fork_branch_name),
        )

        # 4. 构建配置覆写并写入 forked task
        overlay = await self._build_config_overlay(should_feedback)
        forked_task = await get_task(forked_task_id)
        await update_config_overlay(
            forked_task_id,
            dict(forked_task.storage_snapshot) if forked_task and forked_task.storage_snapshot else {},
            overlay,
        )

        # 5. 设置 logic marks
        await self._set_logic_marks(forked_task_id)

        # 6. 构建并批量插入消息
        contents = await self._build_messages(task, should_feedback)

        messages = [
            _U2AUserMessageCreate(
                user_id=self.user_id,
                session_id=self.session_id,
                message_type="text",
                content=msg_content,
                created_by="sub_agent_task",
                status="waiting_agent_ack_user",
                session_task_id=forked_task_id,
                process_priority=20,
            )
            for msg_content in contents
        ]

        await insert_user_messages_from_list(messages)

        # 7. before_process 回调：合并主分支 snapshot 到 forked task
        current_task_id = self.session_task_id

        async def before_process_callback() -> None:
            main_snapshot = await get_nearest_ancestor_storage_snapshot(current_task_id)
            if main_snapshot is None:
                return
            # 重新读取 forked task 以获取最新的 storage_snapshot（含 overlay）
            fresh_forked_task = await get_task(forked_task_id)
            if fresh_forked_task is None:
                return
            new_snapshot = {**main_snapshot}
            if fresh_forked_task.storage_snapshot and SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT in fresh_forked_task.storage_snapshot:
                sub_overlay = fresh_forked_task.storage_snapshot[SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT]
                new_snapshot[SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT] = sub_overlay
            await update_task_storage_snapshot(forked_task_id, new_snapshot)

        # 8. 调度（非阻塞）
        service_name = self._resolve_service_name()
        asyncio.create_task(  # noqa: RUF006
            schedule_pending_task(
                user_id=self.user_id,
                session_id=self.session_id,
                branch_name=fork_branch_name,
                llm_service_name=service_name,
                before_process=before_process_callback,
            )
        )

        if not self.agent_def.disable_completion_callback:
            asyncio.create_task(  # noqa: RUF006
                self._completed_callback(forked_task_id, fork_branch_name, alias, should_feedback)
            )

        return ToolTaskResult(
            str_content=f"子代理 '{self.agent_def.name}' 已在 fork 分支中调度，分支名: `{fork_branch_name}`. 别名：`{alias}`。请男心等待结果。",
            json_content={"branch_name": fork_branch_name},
            occur_error=False,
        )

    # ---
    # 配置覆写
    # ---

    async def _build_config_overlay(self, should_feedback: bool) -> dict:
        """构建 tools_config 与 mcp_config 的 overlay 字典。"""
        overlay: dict[str, Any] = {"tools_config": {}}
        base = await get_base_session_config(session_id=self.session_id)
        all_tool_names = base.tools_config.keys()

        for tool_name in all_tool_names:
            if tool_name in self.agent_def.tools:
                overlay["tools_config"][tool_name] = {"enabled": True}
            else:
                overlay["tools_config"][tool_name] = {"enabled": False}
        # feed_message 特殊处理
        if should_feedback:
            overlay["tools_config"]["feed_message"] = {"enabled": True}
        else:
            overlay["tools_config"]["feed_message"] = {"enabled": False}
        # MCP 配置覆写
        if self.agent_def.mcp_server_config:
            overlay["mcp_config"] = {"$replace": self.agent_def.mcp_server_config.model_dump(mode="json")}
        else:
            overlay["mcp_config"] = {"$replace": None}
        return overlay

    # ---
    # logic marks
    # ---

    async def _set_logic_marks(self, task_id: UUID) -> None:
        """设置必要的 logic mark 标记。"""
        await update_task_logic_mark_field(
            task_id, TO_REMINDER_TOOL_ENABLE_STATUS_MARK_NAME, True,
        )
        await update_task_logic_mark_field(
            task_id, TO_REMINDER_MCP_SERVER_CONFIG_CHANGED_MARK_NAME, True,
        )

    # ---
    # 服务名解析
    # ---

    def _resolve_service_name(self) -> str:
        """解析 LLM 服务名，优先使用 agent 定义中指定的服务。"""
        if self.agent_def.service:
            return self.agent_def.service
        return self.llm_service_name

    # ---
    # 消息构建
    # ---

    async def _build_messages(
        self,
        task: str,
        should_feedback: bool,
    ) -> list[str]:
        """构建子代理的四类用户消息，返回待插入列表。"""
        # 获取调用方分支的 storage_snapshot（用于构建 skill 消息）
        _, caller_snapshot = await get_branch_storage_snapshot(
            session_id=self.session_id,
            user_id=self.user_id,
            branch_name=self.branch_name,
        )

        contents: list[str] = []

        # 1. agent 定义的 system_prompt
        if self.agent_def.system_prompt:
            contents.append(
                (
                    f"{SUB_AGENT_DEF_BLOCK_START}\n"
                    f"{self.agent_def.system_prompt}\n"
                    f"{SUB_AGENT_DEF_BLOCK_END}\n"
                ),
            )

        # 2. hook
        hook_msg = await self._build_hook_message()
        if hook_msg is not None:
            contents.append(hook_msg)

        # 2.5. task 描述文本
        contents.append(
            (
                f"{EXTERNAL_MESSAGE_BLOCK_START}\n"
                "---\n"
                "created_by: sub_agent_task\n"
                f"from: {self.branch_name.split(":")[0]}\n"
                "---\n\n"
                f"{task}\n"
                f"{EXTERNAL_MESSAGE_BLOCK_END}\n"
            ),
        )

        # 3. skills 指令消息
        skill_msg = await build_skill_message(self.agent_def.skills, caller_snapshot)
        if skill_msg is not None:
            contents.append(skill_msg)

        # 4. 反馈说明消息
        if should_feedback:
            contents.append(build_feedback_message(self.branch_name))

        return contents

    # ---
    # before_agent_start_hook
    # ---

    async def _build_hook_message(self) -> str | None:
        """如果 agent 定义中指定了 before_agent_start_hook，在用户容器中执行该脚本，
        返回构建好的消息对象（无输出时返回 None）。"""
        hook_path = self.agent_def.before_agent_start_hook
        if hook_path is None:
            return None

        with logfire.span(
            "sub_agent before_agent_start_hook",
            hook_path=str(hook_path),
            user_id=str(self.user_id),
        ):
            hook_output: str = ""
            hook_error = False

            try:
                async with pod_command_session(user_id=self.user_id) as session:
                    result = await execute_command(
                        pod_command_session_struct=session,
                        command=f"bash {hook_path}",
                        timeout=120.0,
                    )

                if result.returncode == 0 or result.returncode is None:
                    hook_output = result.stdout.strip()
                else:
                    hook_error = True
                    parts = []
                    if result.stderr:
                        parts.append(f"stdout: \n{result.stderr.strip()}")
                    if result.stdout:
                        parts.append(f"stdout: \n{result.stdout.strip()}")
                    hook_output = "\n".join(parts)

            except UserPodCommandError as e:
                hook_error = True
                hook_output = f"before_agent_start_hook 执行失败: {e}"
            except Exception as e:
                hook_error = True
                hook_output = f"before_agent_start_hook 执行异常: {e}"

        prefix = "输出" if not hook_error else "错误输出"
        content = (
            f"{EXTERNAL_MESSAGE_BLOCK_START}\n"
            "---\n"
            "created_by: before_agent_start_hook\n"
            f"from: {self.branch_name.split(':')[0]}\n"
            "---\n\n"
            f"before_agent_start_hook ({hook_path}) {prefix}:\n\n"
            f"{hook_output}\n"
            f"{EXTERNAL_MESSAGE_BLOCK_END}\n"
        )

        return content


    async def _completed_callback(self, task_id: UUID, sub_branch_name: str, alias: str, schedule: bool) -> None:
        # 等待处理完成
        completed_event = RedisEvent(EventNames.session_task_completed(task_id))
        await completed_event.wait()
        # 向调用分支插入完成通知
        msg = (
            f"{SYS_REMINDER_BLOCK_START}\n"
            f"子代理 `{self.agent_def.name}` 已完成，请查看分支 分支名: {sub_branch_name}. 别名：`{alias}`。"
            f"请确认是否按预期受到 feed_message 的消息,或是检查其工作结果。如果不符合预期，使用 feed_message 工具向其发送进一步指令。\n"
            f"{SYS_REMINDER_BLOCK_END}\n"
        )
        calling_barch_pending_task_id, _ = await get_or_create_pending_task(session_id=self.session_id,
                                                                            user_id=self.user_id,
                                                                            branch_name=self.branch_name)
        message_data = _U2AUserMessageCreate(
            user_id=self.user_id,
            session_id=self.session_id,
            message_type="text",
            content=msg,
            created_by="sub_agent_completed_callback",
            status="waiting_agent_ack_user",
            session_task_id=calling_barch_pending_task_id,
            process_priority=20,
        )
        await insert_user_message(message_data)

        if schedule:
            await schedule_pending_task(
                user_id=self.user_id,
                session_id=self.session_id,
                branch_name=self.branch_name,
                llm_service_name=self.llm_service_name,
            )