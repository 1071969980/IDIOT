from uuid import UUID

from ..base import AbstractCommand
from .data_model import GetMcpServersConfigInput, GetMcpServersConfigOutput
from api.agent.session_agent_config.crud import (
    get_base_session_config,
    get_effective_session_config,
)
from api.chat.sql_stat.u2a_session_branch_task.operations import (
    get_or_create_pending_task,
)
from api.chat.sql_stat.u2a_session_task.utils import get_task


class GetMcpServersConfigCommand(
    AbstractCommand[GetMcpServersConfigInput, GetMcpServersConfigOutput]
):

    async def execute(self) -> GetMcpServersConfigOutput:
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

        servers = []
        if effective_config.mcp_config is not None:
            servers = list(effective_config.mcp_config.servers)

        return GetMcpServersConfigOutput(servers=servers)
