from typing import Sequence
from uuid import UUID, uuid4

from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from api.chat.sql_stat.u2a_agent_msg.utils import (
    _U2AAgentMessageCreate,
)
from api.chat.sql_stat.u2a_agent_short_term_memory.utils import (
    _AgentShortTermMemoryCreate,
)

from .node import MemoryNode


class MemoryTree:
    """运行时记忆树，以 ID + 链表范式组织节点。

    _nodes: id -> MemoryNode 查找表
    _branches: branch_name -> leaf_node_id 映射

    同一个节点可以被多个分支共享（同一 leaf_id 出现在多个分支映射中），
    体现"分叉前共享链尾"。
    """

    def __init__(self) -> None:
        self._nodes: dict[UUID, MemoryNode] = {}
        self._branches: dict[str, UUID] = {}

    # --- 链表遍历 ---

    def _walk_root_to_leaf(self, leaf_id: UUID) -> list[MemoryNode]:
        """从 leaf 回溯到 root，返回 root -> leaf 有序列表。"""
        chain: list[MemoryNode] = []
        current_id: UUID | None = leaf_id
        while current_id is not None:
            node = self._nodes[current_id]
            chain.append(node)
            current_id = node.prev_id
        chain.reverse()
        return chain

    # --- 加载 ---

    def load_from_linear(
        self,
        memories: list[ChatCompletionMessageParam],
        branch_name: str,
        bp_indices: set[int] | None = None,
    ) -> None:
        """将线性记忆列表加载为单分支链表。

        Args:
            memories: 线性记忆列表（来自 query_short_term_memory）
            branch_name: 分支名
            bp_indices: 哪些位置是 context_breakpoint
        """
        if bp_indices is None:
            bp_indices = set()

        prev_id: UUID | None = None
        for i, mem in enumerate(memories):
            node = MemoryNode(
                id=uuid4(),
                content=mem,
                prev_id=prev_id,
                is_new=False,
                is_context_breakpoint=i in bp_indices,
            )
            self._nodes[node.id] = node
            prev_id = node.id

        # 最后一个节点作为分支叶子
        if prev_id is not None:
            self._branches[branch_name] = prev_id

    # --- 分支操作 ---

    def add_memories_to_branch(
        self,
        branch_name: str,
        messages: Sequence[ChatCompletionMessageParam],
        mark_new: bool = False,
        to_agent_msg: bool = False,
        is_context_breakpoint: bool = False,
    ) -> list[MemoryNode]:
        """向分支末尾追加多条消息。"""
        nodes: list[MemoryNode] = []
        for msg in messages:
            node = self.append_to_branch(branch_name, msg, is_new=mark_new, to_agent_msg=to_agent_msg, is_context_breakpoint=is_context_breakpoint)
            nodes.append(node)
        return nodes

    def append_to_branch(
        self,
        branch_name: str,
        content: ChatCompletionMessageParam,
        is_new: bool = True,
        to_agent_msg: bool = False,
        is_context_breakpoint: bool = False,
    ) -> MemoryNode:
        """追加单条消息到分支末尾。"""
        prev_id = self._branches.get(branch_name)
        node = MemoryNode(
            id=uuid4(),
            content=content,
            prev_id=prev_id,
            is_new=is_new,
            to_agent_msg=to_agent_msg,
            is_context_breakpoint=is_context_breakpoint,
        )
        self._nodes[node.id] = node
        self._branches[branch_name] = node.id
        return node

    def extend_to_branch(
        self,
        branch_name: str,
        contents: Sequence[ChatCompletionMessageParam],
        is_new: bool = True,
        to_agent_msg: bool = False,
        is_context_breakpoint: bool = False,
    ) -> list[MemoryNode]:
        """批量追加消息到分支末尾。"""
        return self.add_memories_to_branch(branch_name, contents, mark_new=is_new, to_agent_msg=to_agent_msg, is_context_breakpoint=is_context_breakpoint)

    # --- 检索 ---

    def get_branch_linear_memories(
        self,
        branch_name: str,
    ) -> list[ChatCompletionMessageParam]:
        """提取分支线性消息列表（供 LLM 调用）。

        遇到 context_breakpoint 时截断之前的节点（保留断点节点本身及之后）。
        多个断点时只保留最后一个断点之后的节点。
        """
        leaf_id = self._branches.get(branch_name)
        if leaf_id is None:
            return []

        chain = self._walk_root_to_leaf(leaf_id)

        # 找最后一个 context_breakpoint
        last_bp_index = -1
        for i, node in enumerate(chain):
            if node.is_context_breakpoint:
                last_bp_index = i

        # 截断：保留断点节点及之后
        if last_bp_index >= 0:
            chain = chain[last_bp_index:]

        return [node.content for node in chain]

    def get_new_nodes(self, branch_name: str) -> list[MemoryNode]:
        """获取分支上 is_new=True 的节点列表（root -> leaf 顺序）。"""
        leaf_id = self._branches.get(branch_name)
        if leaf_id is None:
            return []
        chain = self._walk_root_to_leaf(leaf_id)
        return [node for node in chain if node.is_new]

    def get_branches(self) -> list[str]:
        """获取所有分支名。"""
        return list(self._branches.keys())

    # --- 持久化 ---

    def extract_db_create_data(
        self,
        branch_name: str,
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID,
    ) -> list[_AgentShortTermMemoryCreate]:
        """提取 DB 持久化数据。只处理 is_new=True 的节点。"""
        new_nodes = self.get_new_nodes(branch_name)
        return [
            _AgentShortTermMemoryCreate(
                user_id=user_id,
                session_id=session_id,
                content=node.content, # type: ignore
                sub_seq_index=index,
                session_task_id=session_task_id,
            )
            for index, node in enumerate(new_nodes)
        ]

    def extract_agent_messages(
        self,
        branch_name: str,
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID,
    ) -> list[_U2AAgentMessageCreate]:
        """从新节点提取 agent 业务消息列表。

        只处理 to_agent_msg=True 且 is_new=True 的节点，按序构建 _U2AAgentMessageCreate：
        - assistant 节点 → text 消息
        - tool 节点（有 tool_task_result）→ tool_call + 可选的 session_link 消息
        """
        new_nodes = self.get_new_nodes(branch_name)
        messages: list[_U2AAgentMessageCreate] = []
        sub_seq_index = 0

        for node in new_nodes:
            if not node.to_agent_msg:
                continue

            role = node.content.get("role")

            if role == "assistant":
                text_content = node.content.get("content", "")
                reasoning = node.content.get("reasoning_content", "")
                messages.append(_U2AAgentMessageCreate(
                    user_id=user_id,
                    session_id=session_id,
                    session_task_id=session_task_id,
                    sub_seq_index=sub_seq_index,
                    message_type="text",
                    content=text_content,
                    status="completed",
                    json_content={"reasoning_content": reasoning},
                ))
                sub_seq_index += 1

            elif role == "tool" and node.tool_task_result is not None:
                result = node.tool_task_result

                messages.append(_U2AAgentMessageCreate(
                    user_id=user_id,
                    session_id=session_id,
                    session_task_id=session_task_id,
                    sub_seq_index=sub_seq_index,
                    message_type="tool_call",
                    content=node.tool_name or "",
                    status="completed",
                    json_content=result.model_dump(mode="json", exclude={"str_content"}),
                ))
                sub_seq_index += 1

                if result.u2a_session_link_data:
                    messages.append(_U2AAgentMessageCreate(
                        user_id=user_id,
                        session_id=session_id,
                        session_task_id=session_task_id,
                        sub_seq_index=sub_seq_index,
                        message_type="u2a_session_link",
                        content=result.u2a_session_link_data.title,
                        status="completed",
                        json_content=result.u2a_session_link_data.model_dump(mode="json"),
                    ))
                    sub_seq_index += 1

                if result.a2a_session_link_data:
                    messages.append(_U2AAgentMessageCreate(
                        user_id=user_id,
                        session_id=session_id,
                        session_task_id=session_task_id,
                        sub_seq_index=sub_seq_index,
                        message_type="a2a_session_link",
                        content=result.a2a_session_link_data.goal,
                        status="completed",
                        json_content=result.a2a_session_link_data.model_dump(mode="json"),
                    ))
                    sub_seq_index += 1

        return messages
