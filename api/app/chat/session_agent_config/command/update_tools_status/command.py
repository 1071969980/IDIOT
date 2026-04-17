from uuid import UUID

from api.agent.logic_mark_def import TO_REMINDER_TOOL_ENABLE_STATUS_MARK_NAME

from ..base import AbstractCommand
from .data_model import (
    UpdateToolsStatusInput,
    UpdateToolsStatusOutput,
    UpdatedToolStatus,
)
from api.agent.session_agent_config.crud import (
    get_base_session_config,
    get_effective_session_config,
    update_config_overlay,
)
from api.chat.sql_stat.u2a_session_branch_task.operations import (
    get_or_create_pending_task,
)
from api.chat.sql_stat.u2a_session_task.utils import (
    get_task,
    update_task_logic_mark_field,
)


class UpdateToolsStatusCommand(
    AbstractCommand[UpdateToolsStatusInput, UpdateToolsStatusOutput]
):

    async def execute(self) -> UpdateToolsStatusOutput:
        session_uuid = UUID(self.session_id)

        # 获取基础配置用于验证工具名称
        base_config = await get_base_session_config(session_uuid)
        available_tools = set(base_config.tools_config.keys())

        # 验证所有工具名称
        for item in self.input_model.tools_status:
            if item.tool_name not in available_tools:
                raise ValueError(f"Unknown tool name: {item.tool_name}")

        # 构建 overlay 字典
        tools_overlay: dict = {}
        for item in self.input_model.tools_status:
            tool_overlay: dict = {"enabled": item.enabled}
            if item.explicit is not None:
                tool_overlay["explicit"] = item.explicit
            tools_overlay[item.tool_name] = tool_overlay

        overlay_updates = {"tools_config": tools_overlay}

        # 解析分支并获取 storage_snapshot
        task_id, _ = await get_or_create_pending_task(
            session_id=session_uuid,
            user_id=UUID(self.user_id),
            branch_name=self.input_model.branch_name,
        )
        task = await get_task(task_id)
        if task is None or task.storage_snapshot is None:
            raise ValueError(f"Task {task_id} or its storage_snapshot not found")
        storage_snapshot = dict(task.storage_snapshot)

        # 写入 overlay
        await update_config_overlay(task_id, storage_snapshot, overlay_updates)
        # 写入 logic_mark
        await update_task_logic_mark_field(task_id, TO_REMINDER_TOOL_ENABLE_STATUS_MARK_NAME, True)

        # 构建响应
        effective_config = get_effective_session_config(base_config, storage_snapshot)
        result = []
        for item in self.input_model.tools_status:
            cfg = effective_config.tools_config[item.tool_name]
            result.append(UpdatedToolStatus(
                tool_name=item.tool_name,
                enabled=cfg.enabled,
                explicit=cfg.explicit,
            ))
        

        return UpdateToolsStatusOutput(updated_tools=result)
