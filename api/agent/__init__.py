async def create_table() -> None:
    # ./agent/sql_stat
    from api.agent.sql_stat.u2a_session_agent_config.utils import (
        create_table as create_u2a_session_agent_config_table,
    )
    await create_u2a_session_agent_config_table()
    from api.agent.sql_stat.u2a_session_storage.utils import (
        create_table as create_u2a_session_storage_table,
    )
    await create_u2a_session_storage_table()