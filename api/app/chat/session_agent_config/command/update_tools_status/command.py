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
    merge_config_overlay,
)
from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_op import (
    update_branch_storage_snapshot,
)
from api.chat.sql_stat.u2a_session_task.utils import update_task_logic_mark_field
from api.sql_utils.utils import SQL_OP_ContextData


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

        # 在锁保护下执行 Read-Modify-Write + logic_mark（同一事务）
        ctx = SQL_OP_ContextData(description="update_tools_status: storage_snapshot + logic_mark")
        try:
            task_id, storage_snapshot = await update_branch_storage_snapshot(
                session_id=session_uuid,
                user_id=UUID(self.user_id),
                branch_name=self.input_model.branch_name,
                update_fn=lambda s: merge_config_overlay(s, overlay_updates),
                ctx=ctx,
            )

            await update_task_logic_mark_field(
                task_id, TO_REMINDER_TOOL_ENABLE_STATUS_MARK_NAME, True,
                ctx=ctx,
            )

            await ctx.commit()
        except Exception:
            await ctx.rollback()
            raise

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
