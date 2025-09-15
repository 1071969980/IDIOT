from sqlalchemy.engine.url import URL
from sqlalchemy import (
    create_engine
)

DEFAULT_DATA_BASE_NAME = "postgres"

sql_url  = URL.create(
    drivername="postgresql",
    username="postgres",
    password="postgres",
    host="postgres",
    port=5432,
    database=str(DEFAULT_DATA_BASE_NAME),
)

SQL_ENGINE = create_engine(sql_url)
DEFAULT_SQL_ENGINE_POOL = SQL_ENGINE.pool