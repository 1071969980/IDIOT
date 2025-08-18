from .user_db_base import UserDBBase
from .simple_user_db import SimpleUserDB

USER_DB : UserDBBase | None = SimpleUserDB()
if USER_DB is None:
    raise ValueError("USER_DB is not set")