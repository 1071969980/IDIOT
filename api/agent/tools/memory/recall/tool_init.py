"""记忆召回 Agent 的工具构造。"""

from uuid import UUID

from api.chat.data_model import ToolInitializationResult
from ..config_data_model import MemoryToolScope


def build_recall_tool_init_res(
    memory_scope: MemoryToolScope,
    session_id: UUID,
    branch_name: str,
) -> ToolInitializationResult:
    """为召回 Agent 构造 ToolInitializationResult。

    仅包含 read_file 和 list_directory（只读工具）。
    return_memory_recall 闭包由 lifecycle hook 动态注入。
    """
    from api.agent.tools.file_operations.read_file.config_data_model import ReadFileConfig
    from api.agent.tools.file_operations.read_file.constructor import construct_read_file
    from api.agent.tools.file_operations.list_directory.config_data_model import ListDirectoryConfig
    from api.agent.tools.file_operations.list_directory.constructor import construct_list_directory

    file_ops_scope = memory_scope.to_file_ops_scope()
    empty_scope_def: dict = {}

    tool_completion_params_map = {}
    tool_closures_map = {}
    enable_tools_set: set[str] = set()
    explicit_tools_set: set[str] = set()

    for config, constructor in [
        (ReadFileConfig(tool_scope=file_ops_scope), construct_read_file),
        (ListDirectoryConfig(tool_scope=file_ops_scope), construct_list_directory),
    ]:
        param, closure = constructor(
            config, empty_scope_def,
            session_id=session_id,
            branch_name=branch_name,
        )
        name = param["function"]["name"]
        tool_completion_params_map[name] = param
        tool_closures_map[name] = closure
        enable_tools_set.add(name)
        explicit_tools_set.add(name)

    return ToolInitializationResult(
        tool_completion_params_map=tool_completion_params_map,
        tool_closures_map=tool_closures_map,
        enable_tools_set=enable_tools_set,
        disable_tools_set=set(),
        explicit_tools_set=explicit_tools_set,
        implicit_tools_set=set(),
    )
