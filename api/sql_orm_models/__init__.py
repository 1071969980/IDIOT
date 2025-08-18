from pathlib import Path

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declarative_base,
    mapped_column,
    relationship,
)

from api.app.sql_orm import (
    ContractReviewTask,
    MarkdownExport,
    SuggestionMergeTask,
    UploadedFile,
)

from api.authentication.sql_orm import (
    SimpleUser,
)

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

