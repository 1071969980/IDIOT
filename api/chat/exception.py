from api.agent.memory_tree import MemoryTree


class SessionChatTaskCancelled(Exception):
    def __init__(self, memory_tree: MemoryTree, mem_branch_name: str):
        super().__init__("SessionChatTaskCancelled")
        self.memory_tree = memory_tree
        self.branch_name = mem_branch_name
