from uuid import UUID

from ..base import AbstractCommand
from .data_model import UpdateMcpServersConfigInput, UpdateMcpServersConfigOutput
from api.agent.session_agent_config.crud import (
    get_base_session_config,
    get_effective_session_config,
    merge_config_overlay,
)
from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_op import (
    update_branch_storage_snapshot,
)


class UpdateMcpServersConfigCommand(
    AbstractCommand[UpdateMcpServersConfigInput, UpdateMcpServersConfigOutput]
):

    async def execute(self) -> UpdateMcpServersConfigOutput:
        session_uuid = UUID(self.session_id)

        base_config = await get_base_session_config(session_uuid)

        # 构建 overlay：将整个 mcp_config 写为 overlay
        servers_data = [
            server.model_dump(mode="json") for server in self.input_model.servers
        ]
        overlay_updates = {
            "mcp_config": {"servers": servers_data}
        }

        # 在锁保护下执行 Read-Modify-Write
        _, storage_snapshot = await update_branch_storage_snapshot(
            session_id=session_uuid,
            user_id=UUID(self.user_id),
            branch_name=self.input_model.branch_name,
            update_fn=lambda s: merge_config_overlay(s, overlay_updates),
        )

        effective = get_effective_session_config(base_config, storage_snapshot)
        servers = []
        if effective.mcp_config is not None:
            servers = list(effective.mcp_config.servers)

        return UpdateMcpServersConfigOutput(servers=servers)
