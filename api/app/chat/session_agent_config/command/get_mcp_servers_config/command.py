from uuid import UUID

from ..base import AbstractCommand
from .data_model import GetMcpServersConfigInput, GetMcpServersConfigOutput
from api.agent.session_agent_config.crud import (
    get_base_session_config,
    get_effective_session_config,
)
from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_op import (
    get_branch_storage_snapshot,
)


class GetMcpServersConfigCommand(
    AbstractCommand[GetMcpServersConfigInput, GetMcpServersConfigOutput]
):

    async def execute(self) -> GetMcpServersConfigOutput:
        session_uuid = UUID(self.session_id)
        base_config = await get_base_session_config(session_uuid)

        branch_name = self.input_model.branch_name
        if branch_name is not None:
            _, storage_snapshot = await get_branch_storage_snapshot(
                session_id=session_uuid,
                user_id=UUID(self.user_id),
                branch_name=branch_name,
            )
            effective_config = get_effective_session_config(
                base_config,
                storage_snapshot=storage_snapshot,
            )
        else:
            effective_config = base_config

        servers = []
        if effective_config.mcp_config is not None:
            servers = list(effective_config.mcp_config.servers)

        return GetMcpServersConfigOutput(servers=servers)
