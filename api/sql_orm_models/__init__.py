from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, mapped_column, relationship, Mapped, DeclarativeBase
from sqlalchemy.engine.url import URL
from sqlalchemy import create_engine
from pathlib import Path

import api.app.sql_orm as api_sql_orm

from .base import Base


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
Base.metadata.create_all(SQL_ENGINE)


__all__ = [
    "SQL_ENGINE",
    "DEFAULT_DATA_BASE_NAME",
    "api_sql_orm",
]
