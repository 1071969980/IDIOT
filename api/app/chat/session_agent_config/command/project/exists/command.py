from uuid import UUID

from api.agent.session_agent_config.crud import (
    get_base_session_config,
    get_effective_session_config,
)
from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_op import (
    get_branch_storage_snapshot,
)

from ...base import AbstractCommand
from .data_model import ProjectExistsInput, ProjectExistsOutput
from ..create.data_model import build_project_rel_path


class ProjectExistsCommand(AbstractCommand[ProjectExistsInput, ProjectExistsOutput]):
    async def execute(self) -> ProjectExistsOutput:
        session_uuid = UUID(self.session_id)
        base_config = await get_base_session_config(session_uuid)

        branch_name = self.input_model.branch_name
        if branch_name is not None:
            _, storage_snapshot = await get_branch_storage_snapshot(
                session_id=session_uuid,
                user_id=UUID(self.user_id),
                branch_name=branch_name,
            )
            effective_config = get_effective_session_config(base_config, storage_snapshot)
        else:
            effective_config = base_config

        project_dir = build_project_rel_path(self.input_model.project_path)
        exists = project_dir in effective_config.allowed_rel_dirs_in_juicefs_for_tool

        return ProjectExistsOutput(
            exists=exists,
            project_path=self.input_model.project_path,
        )
