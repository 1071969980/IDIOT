async def create_table() -> None:
    # ./agent/sql_stat
    from api.agent.sql_stat.u2a_session_agent_config.utils import (
        create_table as create_u2a_session_agent_config_table,
    )
    await create_u2a_session_agent_config_table()

    # ./agent/tools/a2a_chat_task/sql_stat
    from api.agent.tools.a2a_chat_task.sql_stat.a2a_session.utils import (
        create_table as create_a2a_session_table,
    )
    await create_a2a_session_table()

    from api.agent.tools.a2a_chat_task.sql_stat.a2a_session_task.utils import (
        create_table as create_a2a_session_task_table,
    )
    await create_a2a_session_task_table()

    from api.agent.tools.a2a_chat_task.sql_stat.a2a_session_short_term_memory.utils import (
        create_tables as create_a2a_session_short_term_memory_table,
    )
    await create_a2a_session_short_term_memory_table()

    from api.agent.tools.a2a_chat_task.sql_stat.a2a_session_side_msg.utils import (
        create_tables as create_a2a_session_side_msg_table,
    )
    await create_a2a_session_side_msg_table()