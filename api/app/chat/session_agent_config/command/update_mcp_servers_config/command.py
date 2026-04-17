from uuid import UUID

from ..base import AbstractCommand
from .data_model import UpdateMcpServersConfigInput, UpdateMcpServersConfigOutput
from api.agent.session_agent_config.crud import (
    get_base_session_config,
    get_effective_session_config,
    update_config_overlay,
)
from api.chat.sql_stat.u2a_session_branch_task.operations import (
    get_or_create_pending_task,
)
from api.chat.sql_stat.u2a_session_task.utils import get_task
from api.redis.distributed_lock import RedisDistributedLock
from api.redis.lock_names import LockNames


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

        # 解析分支并获取 storage_snapshot
        task_id, _ = await get_or_create_pending_task(
            session_id=session_uuid,
            user_id=UUID(self.user_id),
            branch_name=self.input_model.branch_name,
        )

        # 在锁保护下执行 Read-Judge-Write
        lock_key = LockNames.task_storage_snapshot(task_id)
        async with RedisDistributedLock(lock_key):
            task = await get_task(task_id)
            if task is None or task.storage_snapshot is None:
                raise ValueError(f"Task {task_id} or its storage_snapshot not found")
            storage_snapshot = dict(task.storage_snapshot)

            await update_config_overlay(task_id, storage_snapshot, overlay_updates)

        effective = get_effective_session_config(base_config, storage_snapshot)
        servers = []
        if effective.mcp_config is not None:
            servers = list(effective.mcp_config.servers)

        return UpdateMcpServersConfigOutput(servers=servers)
