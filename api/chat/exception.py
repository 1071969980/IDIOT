from api.agent.memory_tree import MemoryTrails


class SessionChatTaskCancelled(Exception):
    def __init__(self, memory_trails: MemoryTrails, mem_marker_name: str):
        super().__init__("SessionChatTaskCancelled")
        self.memory_trails = memory_trails
        self.marker_name = mem_marker_name
