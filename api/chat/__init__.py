from .sql_stat.u2a_user_msg.utils import create_table as create_u2a_msg_table
from .sql_stat.u2a_session.utils import create_table as create_u2a_session_table

create_u2a_msg_table()
create_u2a_session_table()