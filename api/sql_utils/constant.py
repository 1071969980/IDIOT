import os

from sqlalchemy.engine.url import URL
from sqlalchemy import (
    create_engine,
)
from sqlalchemy.ext.asyncio import create_async_engine

DEFAULT_DATA_BASE_NAME = "postgres"

# 主 PostgreSQL (保持短名称，同命名空间)
sql_url = URL.create(
    drivername="postgresql",
    username="postgres",
    password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
    host="postgres",
    port=5432,
    database=str(DEFAULT_DATA_BASE_NAME),
)
async_sql_url = URL.create(
    drivername="postgresql+asyncpg",
    username="postgres",
    password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
    host="postgres",
    port=5432,
    database=str(DEFAULT_DATA_BASE_NAME),
)

# JuiceFS PostgreSQL (跨命名空间，使用 FQDN)
_juicefs_postgres_password = os.environ.get("JUICEFS_POSTGRES_PASSWORD", "juicefs-postgres")
juice_fs_metadata_sql_url = URL.create(
    drivername="postgresql",
    username="postgres",
    password=_juicefs_postgres_password,
    host="juicefs-postgres.idiot-user-space-storage.svc.cluster.local",
    port=5432,
)

juice_fs_metadata_async_sql_url = URL.create(
    drivername="postgresql+asyncpg",
    username="postgres",
    password=_juicefs_postgres_password,
    host="juicefs-postgres.idiot-user-space-storage.svc.cluster.local",
    port=5432,
)

SQL_ENGINE = create_engine(sql_url)
ASYNC_SQL_ENGINE = create_async_engine(async_sql_url, future=True)
DEFAULT_SQL_ENGINE_POOL = SQL_ENGINE.pool

JUICE_FS_METADATA_SQLENGINE = create_engine(juice_fs_metadata_sql_url)
JUICE_FS_METADATA_ASYNC_SQLENGINE = create_async_engine(juice_fs_metadata_async_sql_url, future=True)
DEFAULT_JUICE_FS_METADATA_SQL_ENGINE_POOL = JUICE_FS_METADATA_SQLENGINE.pool