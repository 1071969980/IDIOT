from sqlalchemy.engine.url import URL
from sqlalchemy import (
    create_engine,
)
from sqlalchemy.ext.asyncio import create_async_engine

from api.core.env_config import service_config, storage_config

DEFAULT_DATA_BASE_NAME = "postgres"

# 主 PostgreSQL (保持短名称，同命名空间)
_postgres_password = storage_config.postgres_password.get_secret_value()
sql_url = URL.create(
    drivername="postgresql",
    username="postgres",
    password=_postgres_password,
    host="postgres",
    port=5432,
    database=str(DEFAULT_DATA_BASE_NAME),
)
async_sql_url = URL.create(
    drivername="postgresql+asyncpg",
    username="postgres",
    password=_postgres_password,
    host="postgres",
    port=5432,
    database=str(DEFAULT_DATA_BASE_NAME),
)

# JuiceFS PostgreSQL (跨命名空间，使用 FQDN)
_juicefs_postgres_password = storage_config.juicefs_postgres_password.get_secret_value()
juice_fs_metadata_sql_url = URL.create(
    drivername="postgresql",
    username="postgres",
    password=_juicefs_postgres_password,
    host=service_config.juicefs_postgres_host,
    port=5432,
)

juice_fs_metadata_async_sql_url = URL.create(
    drivername="postgresql+asyncpg",
    username="postgres",
    password=_juicefs_postgres_password,
    host=service_config.juicefs_postgres_host,
    port=5432,
)

# 连接池通用配置
_ENGINE_KWARGS = {
    "future": True,
    "pool_pre_ping": True,  # 使用前检查连接有效性，解决 connection is closed 问题
    "pool_recycle": 1800,   # 每30分钟回收连接，避免长时间空闲连接失效
    "pool_size": 5,
    "max_overflow": 10,
}

SQL_ENGINE = create_engine(sql_url)
ASYNC_SQL_ENGINE = create_async_engine(async_sql_url, **_ENGINE_KWARGS)
DEFAULT_SQL_ENGINE_POOL = SQL_ENGINE.pool

JUICE_FS_METADATA_SQLENGINE = create_engine(juice_fs_metadata_sql_url)
JUICE_FS_METADATA_ASYNC_SQLENGINE = create_async_engine(juice_fs_metadata_async_sql_url, **_ENGINE_KWARGS)
DEFAULT_JUICE_FS_METADATA_SQL_ENGINE_POOL = JUICE_FS_METADATA_SQLENGINE.pool