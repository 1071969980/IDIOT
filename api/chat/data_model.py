from dataclasses import dataclass

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.type import ToolClosure


@dataclass
class ToolInitializationResult:
    tool_completion_params_map: dict[str, ChatCompletionToolParam]
    tool_closures_map: dict[str, ToolClosure]
    enable_tools_set: set[str]
    disable_tools_set: set[str]
    explicit_tools_set: set[str]
    implicit_tools_set: set[str]

    def merge_inplace(self, other: "ToolInitializationResult"):
        all_self_tools = set(self.tool_completion_params_map.keys())
        does_conflict = set(other.tool_completion_params_map.keys()).intersection(all_self_tools)
        if does_conflict:
            raise ValueError(f"dublicate tool name: {does_conflict} when merging")
        
        self.tool_completion_params_map.update(other.tool_completion_params_map)
        self.tool_closures_map.update(other.tool_closures_map)
        self.enable_tools_set.update(other.enable_tools_set)
        self.disable_tools_set.update(other.disable_tools_set)
        self.explicit_tools_set.update(other.explicit_tools_set)
        self.implicit_tools_set.update(other.implicit_tools_set)