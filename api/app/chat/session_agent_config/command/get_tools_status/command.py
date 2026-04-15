from uuid import UUID

from ..base import AbstractCommand
from .data_model import GetToolsStatusInput, GetToolsStatusOutput, ToolStatus
from api.agent.session_agent_config.crud import (
    get_base_session_config,
    get_effective_session_config,
)
from api.chat.sql_stat.u2a_session_branch_task.operations import (
    get_or_create_pending_task,
)
from api.chat.sql_stat.u2a_session_task.utils import get_task


class GetToolsStatusCommand(AbstractCommand[GetToolsStatusInput, GetToolsStatusOutput]):

    async def execute(self) -> GetToolsStatusOutput:
        session_uuid = UUID(self.session_id)
        base_config = await get_base_session_config(session_uuid)

        branch_name = self.input_model.branch_name
        if branch_name is not None:
            task_id, _ = await get_or_create_pending_task(
                session_id=session_uuid,
                user_id=UUID(self.user_id),
                branch_name=branch_name,
            )
            task = await get_task(task_id)
            effective_config = get_effective_session_config(
                base_config,
                storage_snapshot=dict(task.storage_snapshot) if task and task.storage_snapshot else None,
            )
        else:
            effective_config = base_config

        available_tools = set(effective_config.tools_config.keys())

        requested = self.input_model.tool_names
        if requested:
            invalid = set(requested) - available_tools
            if invalid:
                raise ValueError(f"Unknown tool names: {invalid}")
            target_tools = requested
        else:
            target_tools = list(available_tools)

        result = []
        for name in target_tools:
            cfg = effective_config.tools_config[name]
            result.append(ToolStatus(
                tool_name=name,
                enabled=cfg.enabled,
                explicit=cfg.explicit,
            ))

        return GetToolsStatusOutput(tools_status=result)
