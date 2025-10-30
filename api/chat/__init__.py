def create_table() -> None:
    from .sql_stat.u2a_agent_msg.utils import create_table as create_u2a_agent_msg_table
    from .sql_stat.u2a_agent_short_term_memory.utils import (
        create_table as create_u2a_agent_short_term_memory_table,
    )
    from .sql_stat.u2a_session.utils import create_table as create_u2a_session_table
    from .sql_stat.u2a_user_msg.utils import create_table as create_u2a_user_msg_table
    from .sql_stat.u2a_user_short_term_memory.utils import (
        create_table as create_u2a_user_short_term_memory_table,
    )

    create_u2a_session_table()
    create_u2a_user_msg_table()
    create_u2a_agent_msg_table()
    create_u2a_user_short_term_memory_table()
    create_u2a_agent_short_term_memory_table()
