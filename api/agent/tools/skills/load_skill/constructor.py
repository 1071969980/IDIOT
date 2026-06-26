# api/agent/tools/skills/load_skill/constructor.py

"""load_skill 工具的构造器和实现。"""

import asyncio
from pathlib import PurePosixPath
from typing import Any, cast
from uuid import UUID

from pydantic import ValidationError
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.type import ToolClosure, UserToolCallingPermissionRole
from api.agent.tools.skills.definition_loader import (
    load_all_skill_infos,
    load_skill_by_directory,
)
from api.agent.tools.skills.data_model import SkillLoadResult, SkillDefinition, SkillInfo
from api.agent.session_agent_config.utils import resolve_scope_value
from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_keys import StorageSnapshotKeys

from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_op import (
    update_branch_storage_snapshot,
)

from .config_data_model import (
    LoadSkillConfig,
    LoadSkillParamDefine,
    LOAD_SKILL_GENERATION_TOOL_PARAM,
    SkillToolScope,
    LOAD_SKILL_PROJ_PATHS,
    LOAD_SKILL_ROLE_PATHS,
    LOAD_SKILL_USER_ID_PATHS,
    TOOL_NAME,
)
from .utils import _format_skill_info

# 用于在 update_fn 闭包中传递 skill_name 和标记重复
_DuplicateMark = object()


class LoadSkillTool:
    """加载技能信息的工具。"""

    def __init__(
        self,
        config: LoadSkillConfig,
        user_id: UUID,
        session_id: UUID,
        branch_name: str,
    ):
        self.config = config
        # 会话拥有者：LOADED_SKILLS 等 storage_snapshot 以其为键。
        # 注意区别于 scope.user_id_for_scope ——后者决定从哪个用户空间「读取技能定义」，两者不一定相同。
        self.user_id = user_id
        self.session_id = session_id
        self.branch_name = branch_name
        # 技能简要信息缓存：披露名 -> SkillInfo
        self._skill_infos: dict[str, SkillInfo] | None = None

    async def _ensure_skill_infos_loaded(
        self, cancel_event: asyncio.Event | None = None,
    ) -> dict[str, SkillInfo]:
        """确保技能简要信息已加载（延迟加载 + 缓存）。

        返回「披露名 -> SkillInfo」，供生命周期钩子（披露列表）与 __call__（指名解析）共享。
        """
        if self._skill_infos is None:
            scope = self.config.tool_scope
            if scope is None:
                self._skill_infos = {}
            else:
                self._skill_infos = await load_all_skill_infos(
                    scope.user_id_for_scope,
                    role=scope.role,
                    proj_paths=scope.proj_paths,
                    cancel_event=cancel_event,
                )
        return self._skill_infos

    async def get_skill_definition(
        self, disclosed_name: str,
        cancel_event: asyncio.Event | None = None,
    ) -> SkillDefinition | None:
        """按披露名解析并加载完整技能定义。

        通过 _ensure_skill_infos_loaded 的缓存把披露名解析为 SkillInfo.path，再定点加载完整定义。
        披露名不在缓存中、scope 未配置或加载失败时返回 None。
        """
        infos = await self._ensure_skill_infos_loaded(cancel_event=cancel_event)
        info = infos.get(disclosed_name)
        if info is None:
            return None
        scope = self.config.tool_scope
        if scope is None:
            return None
        try:
            return await load_skill_by_directory(scope.user_id_for_scope, info.path,
                                                  cancel_event=cancel_event)
        except Exception:
            return None

    async def cleanup_loaded_skills(
        self, valid_names: set[str]
    ) -> tuple[list[str], list[str]]:
        """从 LOADED_SKILLS 移除不在 valid_names 内的孤儿披露名。

        Args:
            valid_names: 当前仍可用的披露名集合。

        Returns:
            (removed, remaining): 被移除的披露名、清理后仍保留的披露名。
            两者来自同一次加锁快照读，内部一致；无变化时 removed 为空。

        校验时机：
        - on_agent_start：valid_names 传本次刷新的披露名集合；
        - 压缩时：先 reload_skill_infos() 刷新缓存，再传刷新后的披露名集合。
        """
        scope = self.config.tool_scope
        if scope is None:
            return [], []

        result_holder: list[tuple[list[str], list[str]]] = []

        def _filter(snapshot: dict[str, Any]) -> bool:
            loaded: list[str] = snapshot.get(StorageSnapshotKeys.LOADED_SKILLS, [])
            # 已加载非空但本次未命中任何项时不清空。
            if loaded and not valid_names:
                result_holder.append(([], list(loaded)))
                return False
            cleaned = [s for s in loaded if s in valid_names]
            removed = [s for s in loaded if s not in valid_names]
            result_holder.append((removed, cleaned))
            if not removed:
                return False
            snapshot[StorageSnapshotKeys.LOADED_SKILLS] = cleaned
            return True

        try:
            await update_branch_storage_snapshot(
                session_id=self.session_id,
                user_id=self.user_id,
                branch_name=self.branch_name,
                update_fn=_filter,
            )
        except Exception:
            return [], []

        return result_holder[0] if result_holder else ([], [])

    async def reload_skill_infos(
        self, cancel_event: asyncio.Event | None = None,
    ) -> dict[str, SkillInfo]:
        """失效缓存并重新扫描技能定义。

        供压缩等需要最新盘上状态的时刻使用：压缩时应先刷新定义，
        再据其结果清理 LOADED_SKILLS，最后重新读取技能内容。
        """
        self._skill_infos = None
        return await self._ensure_skill_infos_loaded(cancel_event=cancel_event)

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        # 在 Pydantic 验证前提取 cancel_event
        cancel_event = cast(asyncio.Event | None, kwargs.get("cancel_event"))

        # 入口 fast-return
        if cancel_event is not None and cancel_event.is_set():
            return ToolTaskResult(
                str_content="技能加载已被用户取消",
                occur_error=True,
            )

        # 参数验证
        try:
            param = LoadSkillParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join(
                f"{'.'.join(str(l) for l in err['loc'])} - {err['msg']}"
                for err in e.errors()
            )
            return ToolTaskResult(
                str_content=f"参数验证失败:\n{error_msg}",
                occur_error=True
            )

        scope = self.config.tool_scope
        if scope is None:
            return ToolTaskResult(
                str_content="load_skill 工具未正确配置 tool_scope",
                occur_error=True,
            )

        # 通过缓存的「披露名 -> SkillInfo」解析并定点加载完整定义。
        # 披露名 = 技能显示名（无冲突）或 /dist_fs/... 容器路径（重名）。
        skill_def = await self.get_skill_definition(param.name, cancel_event=cancel_event)
        if skill_def is None:
            return ToolTaskResult(
                str_content=(
                    f"未找到技能: {param.name}"
                    "（请使用 /dist_fs/... 完整路径的完整路径进行调用）"
                ),
                occur_error=True,
            )

        # 用于在闭包中标记是否重复
        result_holder: list[Any] = []

        def _update_loaded_skills(snapshot: dict[str, Any]) -> bool:
            loaded_skills: list[str] = snapshot.setdefault(StorageSnapshotKeys.LOADED_SKILLS, [])
            # LOADED_SKILLS 存「披露名」（= param.name）
            if param.name in loaded_skills:
                result_holder.append(_DuplicateMark)
                return False
            snapshot[StorageSnapshotKeys.LOADED_SKILLS] = [*loaded_skills, param.name]
            return True

        # 在锁保护下更新技能加载状态（LOADED_SKILLS 属于会话拥有者的快照）
        await update_branch_storage_snapshot(
            session_id=self.session_id,
            user_id=self.user_id,
            branch_name=self.branch_name,
            update_fn=_update_loaded_skills,
        )

        if result_holder and result_holder[0] is _DuplicateMark:
            return ToolTaskResult(
                str_content=f" {skill_def.name} 技能已加载, 请勿重复调用",
                occur_error=True
            )

        # 格式化输出
        str_content = _format_skill_info(skill_def)

        json_content = SkillLoadResult(
            name=skill_def.name,
            description=skill_def.description,
            directory_path=skill_def.directory_path,
            directory_tree=skill_def.directory_tree,
            skill_md_content=skill_def.skill_md_content,
            available_resources={
                "template": skill_def.has_template,
                "examples": skill_def.has_examples,
                "scripts": skill_def.has_scripts,
            }
        ).model_dump()

        return ToolTaskResult(
            str_content=str_content,
            json_content=json_content,
            occur_error=False
        )


def construct_load_skill(
    config: LoadSkillConfig,
    scope_def: dict[str, Any],
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """构造 load_skill 工具实例。

    Args:
        config: 工具配置
        scope_def: 作用域定义字典
        **kwargs: 注入参数

    Returns:
        (工具参数, 工具闭包) 元组

    Raises:
        ValueError: 缺少必需参数或配置无效时
    """
    user_id: UUID | None = kwargs.get("user_id")  # 会话拥有者（storage_snapshot 键）
    session_id: UUID | None = kwargs.get("session_id")
    branch_name: str | None = kwargs.get("branch_name")

    if user_id is None:
        raise ValueError("user_id is required")
    if session_id is None:
        raise ValueError("session_id is required")
    if branch_name is None:
        raise ValueError("branch_name is required")

    # 优先级 1: config 已有 tool_scope
    scope = config.tool_scope

    # 优先级 2: 从 scope_def 解析
    if scope is None:
        # 注意：这里解析的是「作用域用户」user_id_for_scope（决定从哪个用户空间读取
        # 技能定义），与上面的会话拥有者 user_id 是两个概念，不一定相同。
        scope_user_id_raw = resolve_scope_value(scope_def, LOAD_SKILL_USER_ID_PATHS)
        scope_user_id = UUID(scope_user_id_raw) if isinstance(scope_user_id_raw, str) else scope_user_id_raw
        role_raw = resolve_scope_value(scope_def, LOAD_SKILL_ROLE_PATHS)
        role = UserToolCallingPermissionRole(role_raw) if isinstance(role_raw, str) else role_raw
        proj_paths_raw = resolve_scope_value(scope_def, LOAD_SKILL_PROJ_PATHS) or []
        proj_paths = [PurePosixPath(p) if isinstance(p, str) else p for p in proj_paths_raw]

        scope = SkillToolScope(
            user_id_for_scope=scope_user_id,
            role=role,
            proj_paths=proj_paths,
        )

    # 将 scope 写入 config
    config = config.model_copy(update={"tool_scope": scope})

    tool = LoadSkillTool(
        config=config,
        user_id=user_id,
        session_id=session_id,
        branch_name=branch_name,
    )

    return (LOAD_SKILL_GENERATION_TOOL_PARAM, tool)


CONSTRUCTOR = {TOOL_NAME: construct_load_skill}
