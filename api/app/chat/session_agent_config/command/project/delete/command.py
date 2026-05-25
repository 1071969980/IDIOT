from uuid import UUID

from api.agent.session_agent_config.crud import (
    get_base_session_config,
    get_effective_session_config,
    merge_config_overlay,
)
from api.agent.session_agent_config.utils import REPLACE_MARKER
from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_op import (
    get_branch_storage_snapshot,
    update_branch_storage_snapshot,
)

from ...base import AbstractCommand
from ..create.data_model import build_memory_rel_path, build_project_rel_path
from .data_model import DeleteProjectInput, DeleteProjectOutput


class DeleteProjectCommand(AbstractCommand[DeleteProjectInput, DeleteProjectOutput]):
    async def execute(self) -> DeleteProjectOutput:
        session_uuid = UUID(self.session_id)

        base_config = await get_base_session_config(session_uuid)
        _, storage_snapshot = await get_branch_storage_snapshot(
            session_id=session_uuid,
            user_id=UUID(self.user_id),
            branch_name=self.input_model.branch_name,
        )
        effective_config = get_effective_session_config(base_config, storage_snapshot)

        current_dirs = effective_config.allowed_rel_dirs_in_juicefs_for_tool

        project_dir = build_project_rel_path(self.input_model.project_path)
        memory_dir = build_memory_rel_path(self.input_model.project_path)

        new_dirs = [d for d in current_dirs if d != project_dir and d != memory_dir]

        overlay_updates = {
            "allowed_rel_dirs_in_juicefs_for_tool": {
                REPLACE_MARKER: [str(p) for p in new_dirs],
            },
        }

        await update_branch_storage_snapshot(
            session_id=session_uuid,
            user_id=UUID(self.user_id),
            branch_name=self.input_model.branch_name,
            update_fn=lambda s: merge_config_overlay(s, overlay_updates),
        )

        return DeleteProjectOutput(
            success=True,
            project_path=self.input_model.project_path,
        )
