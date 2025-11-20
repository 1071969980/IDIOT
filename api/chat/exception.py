from api.chat.sql_stat.u2a_agent_msg.utils import _U2AAgentMessageCreate
from api.chat.sql_stat.u2a_agent_short_term_memory.utils import _AgentShortTermMemoryCreate


class SessionChatTaskCancelled(Exception):
    def __init__(self,
                new_agent_memory: list[_AgentShortTermMemoryCreate],
                new_agent_message: list[_U2AAgentMessageCreate]):
        super().__init__("SessionChatTaskCancelled")
        self.new_agent_memory = new_agent_memory
        self.new_agent_message = new_agent_message
