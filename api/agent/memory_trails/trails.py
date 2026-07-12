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


class MemoryTrailsError(RuntimeError):
    """MemoryTrails 异常基类。"""


class MemoryTrailsIntegrityError(MemoryTrailsError):
    """节点链完整性异常：prev_id 指向不存在的节点。"""


class MemoryTrailsMarkerNotFoundError(MemoryTrailsError):
    """访问不存在的标记。"""


class MemoryTrailsMarkerExistsError(MemoryTrailsError):
    """创建已存在的标记。"""


class MemoryTrails:
    """运行时记忆路径集，以 ID + 链表范式组织节点。

    _nodes: id -> MemoryNode 查找表
    _markers: marker_name -> leaf_node_id 映射

    同一个节点可以被多个标记共享（同一 leaf_id 出现在多个标记映射中），
    体现"分叉前共享链尾"。
    """

    def __init__(self) -> None:
        self.trails_id: UUID = uuid4()
        self._nodes: dict[UUID, MemoryNode] = {}
        self._markers: dict[str, UUID | None] = {}

    # --- 链表遍历 ---

    def _walk_root_to_leaf(self, leaf_id: UUID) -> list[MemoryNode]:
        """从 leaf 回溯到 root，返回 root -> leaf 有序列表。

        Raises:
            MemoryTrailsIntegrityError: prev_id 指向不存在的节点。
        """
        chain: list[MemoryNode] = []
        current_id: UUID | None = leaf_id
        while current_id is not None:
            node = self._nodes.get(current_id)
            if node is None:
                if chain:
                    raise MemoryTrailsIntegrityError(
                        f"Dangling prev_id: node {chain[-1].id} references "
                        f"non-existent node {current_id}"
                    )
                raise MemoryTrailsIntegrityError(
                    f"Marker leaf node {current_id} not found in _nodes"
                )
            chain.append(node)
            current_id = node.prev_id
        chain.reverse()
        return chain

    def _require_marker(self, marker_name: str) -> UUID | None:
        """获取标记 leaf_id，空标记返回 None。

        Raises:
            MemoryTrailsMarkerNotFoundError: 标记不存在。
        """
        if marker_name not in self._markers:
            raise MemoryTrailsMarkerNotFoundError(
                f"Marker '{marker_name}' not found. "
                f"Available: {list(self._markers.keys())}"
            )
        return self._markers[marker_name]

    # --- 标记生命周期 ---

    def create_marker(
        self,
        name: str,
        memories: list[ChatCompletionMessageParam] | None = None,
        bp_indices: set[int] | None = None,
    ) -> None:
        """显式创建标记，可选地预加载历史记忆。

        Args:
            name: 标记名
            memories: 可选的历史记忆列表，为空则创建空标记
            bp_indices: 哪些位置是 context_breakpoint

        Raises:
            MemoryTrailsMarkerExistsError: 标记已存在
        """
        if name in self._markers:
            raise MemoryTrailsMarkerExistsError(
                f"Marker '{name}' already exists"
            )

        if not memories:
            self._markers[name] = None
            return

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

        self._markers[name] = prev_id

    def fork_marker(self, source: str, target: str) -> None:
        """从已有标记的当前 leaf 分叉出新标记，共享节点链。

        Args:
            source: 源标记名（必须存在）
            target: 目标标记名（必须不存在）

        Raises:
            MemoryTrailsMarkerNotFoundError: source 不存在
            MemoryTrailsMarkerExistsError: target 已存在
        """
        if target in self._markers:
            raise MemoryTrailsMarkerExistsError(
                f"Marker '{target}' already exists"
            )
        self._markers[target] = self._require_marker(source)

    # --- 标记操作 ---

    def add_memories_to_marker(
        self,
        marker_name: str,
        messages: Sequence[ChatCompletionMessageParam],
        mark_new: bool = False,
        to_agent_msg: bool = False,
        is_context_breakpoint: bool = False,
    ) -> list[MemoryNode]:
        """向标记末尾追加多条消息。"""
        nodes: list[MemoryNode] = []
        for msg in messages:
            node = self.append_to_marker(marker_name, msg, is_new=mark_new, to_agent_msg=to_agent_msg, is_context_breakpoint=is_context_breakpoint)
            nodes.append(node)
        return nodes

    def append_to_marker(
        self,
        marker_name: str,
        content: ChatCompletionMessageParam,
        is_new: bool = True,
        to_agent_msg: bool = False,
        is_context_breakpoint: bool = False,
    ) -> MemoryNode:
        """追加单条消息到标记末尾。标记必须已通过 create_marker 创建。

        Raises:
            MemoryTrailsMarkerNotFoundError: 标记不存在
        """
        prev_id = self._require_marker(marker_name)
        node = MemoryNode(
            id=uuid4(),
            content=content,
            prev_id=prev_id,
            is_new=is_new,
            to_agent_msg=to_agent_msg,
            is_context_breakpoint=is_context_breakpoint,
        )
        self._nodes[node.id] = node
        self._markers[marker_name] = node.id
        return node

    def rollback_marker(self, marker_name: str, target_node_id: UUID | None) -> None:
        """回滚标记到指定节点，删除之后追加的所有节点。

        从当前叶节点回溯到 target_node_id，移除途径的全部中间节点，
        并将标记指针重置为 target_node_id。

        Args:
            marker_name: 要回滚的标记名。
            target_node_id: 回滚目标节点。严格删除链上此节点之后的所有节点。
                若为 None 则删除全部节点，标记变为空（leaf = None）。

        Raises:
            MemoryTrailsMarkerNotFoundError: 标记不存在。
            MemoryTrailsIntegrityError: target_node_id 不在标记链上，
                或回滚会删除其他标记的叶节点。
        """
        current_leaf = self._require_marker(marker_name)

        # 快速路径：savepoint 以来无新增节点
        if current_leaf == target_node_id:
            return

        # 从 current_leaf 回溯到 target_node_id，收集待删除节点
        to_remove: list[UUID] = []
        cursor: UUID | None = current_leaf

        while cursor is not None and cursor != target_node_id:
            to_remove.append(cursor)
            node = self._nodes.get(cursor)
            if node is None:
                raise MemoryTrailsIntegrityError(
                    f"Dangling prev_id: node {cursor} not found in _nodes"
                )
            cursor = node.prev_id

        # 回溯结束但未找到 target_node_id → 不在链上
        if cursor is None and target_node_id is not None:
            raise MemoryTrailsIntegrityError(
                f"Target node {target_node_id} is not in the chain of "
                f"marker '{marker_name}'"
            )

        # 安全检查：禁止删除其他 marker 的叶节点
        remove_set = set(to_remove)
        for other_name, other_leaf in self._markers.items():
            if other_name == marker_name:
                continue
            if other_leaf is not None and other_leaf in remove_set:
                raise MemoryTrailsIntegrityError(
                    f"Cannot rollback marker '{marker_name}': node "
                    f"{other_leaf} is the leaf of marker '{other_name}'"
                )

        # 执行删除
        for node_id in to_remove:
            del self._nodes[node_id]

        # 重置标记指针
        self._markers[marker_name] = target_node_id

    def extend_to_marker(
        self,
        marker_name: str,
        contents: Sequence[ChatCompletionMessageParam],
        is_new: bool = True,
        to_agent_msg: bool = False,
        is_context_breakpoint: bool = False,
    ) -> list[MemoryNode]:
        """批量追加消息到标记末尾。"""
        return self.add_memories_to_marker(marker_name, contents, mark_new=is_new, to_agent_msg=to_agent_msg, is_context_breakpoint=is_context_breakpoint)

    # --- 检索 ---

    def get_marker_linear_memories(
        self,
        marker_name: str,
    ) -> list[ChatCompletionMessageParam]:
        """提取标记线性消息列表（供 LLM 调用）。

        遇到 context_breakpoint 时截断之前的节点（保留断点节点本身及之后）。
        多个断点时只保留最后一个断点之后的节点。
        """
        leaf_id = self._require_marker(marker_name)
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

    def get_new_nodes(self, marker_name: str) -> list[MemoryNode]:
        """获取标记上 is_new=True 的节点列表（root -> leaf 顺序）。"""
        leaf_id = self._require_marker(marker_name)
        if leaf_id is None:
            return []
        chain = self._walk_root_to_leaf(leaf_id)
        return [node for node in chain if node.is_new]

    def get_markers(self) -> list[str]:
        """获取所有标记名。"""
        return list(self._markers.keys())

    # --- 持久化 ---

    def extract_db_create_data(
        self,
        marker_name: str,
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID,
    ) -> list[_AgentShortTermMemoryCreate]:
        """提取 DB 持久化数据。只处理 is_new=True 的节点。"""
        new_nodes = self.get_new_nodes(marker_name)
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
        marker_name: str,
        user_id: UUID,
        session_id: UUID,
        session_task_id: UUID,
    ) -> list[_U2AAgentMessageCreate]:
        """从新节点提取 agent 业务消息列表。

        只处理 to_agent_msg=True 且 is_new=True 的节点，按序构建 _U2AAgentMessageCreate：
        - assistant 节点 → text 消息
        - tool 节点（有 tool_task_result）→ tool_call + 可选的 session_link 消息
        """
        new_nodes = self.get_new_nodes(marker_name)
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
