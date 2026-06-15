"""记忆写入 Agent 的工具构造。"""

from uuid import UUID

from api.chat.data_model import ToolInitializationResult
from ..config_data_model import MemoryToolScope


def build_write_tool_init_res(
    memory_scope: MemoryToolScope,
    session_id: UUID,
    branch_name: str,
) -> ToolInitializationResult:
    """为写入 Agent 构造 ToolInitializationResult。

    包含 read_file、list_directory、write_file（读写工具）+ bash。
    """
    from api.agent.tools.file_operations.read_file.config_data_model import ReadFileConfig
    from api.agent.tools.file_operations.read_file.constructor import construct_read_file
    from api.agent.tools.file_operations.list_directory.config_data_model import ListDirectoryConfig
    from api.agent.tools.file_operations.list_directory.constructor import construct_list_directory
    from api.agent.tools.file_operations.write_file.config_data_model import WriteFileConfig
    from api.agent.tools.file_operations.write_file.constructor import construct_write_file
    from api.agent.tools.bash.config_data_model import BashConfig
    from api.agent.tools.bash.constructor import construct_tool as construct_bash_tool

    file_ops_scope = memory_scope.to_file_ops_scope()
    empty_scope_def: dict = {}

    tool_completion_params_map = {}
    tool_closures_map = {}
    enable_tools_set: set[str] = set()
    explicit_tools_set: set[str] = set()

    for config, constructor in [
        (ReadFileConfig(tool_scope=file_ops_scope), construct_read_file),
        (ListDirectoryConfig(tool_scope=file_ops_scope), construct_list_directory),
        (WriteFileConfig(tool_scope=file_ops_scope), construct_write_file),
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

    # bash 不走 scope_def 范式，直接传 user_id_for_scope
    bash_param, bash_closure = construct_bash_tool(
        BashConfig(),
        user_id_for_scope=memory_scope.user_id_for_scope,
    )
    bash_name = bash_param["function"]["name"]
    tool_completion_params_map[bash_name] = bash_param
    tool_closures_map[bash_name] = bash_closure
    enable_tools_set.add(bash_name)
    explicit_tools_set.add(bash_name)

    return ToolInitializationResult(
        tool_completion_params_map=tool_completion_params_map,
        tool_closures_map=tool_closures_map,
        enable_tools_set=enable_tools_set,
        disable_tools_set=set(),
        explicit_tools_set=explicit_tools_set,
        implicit_tools_set=set(),
    )
