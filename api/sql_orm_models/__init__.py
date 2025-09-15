from pathlib import Path

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    MetaData
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    SessionTransaction,
    declarative_base,
    mapped_column,
    relationship,
)
from sqlalchemy.event import listen
from sqlalchemy.sql import text

from .base import Base, TenantBase
from .constant import (
    SQL_ENGINE,
)

# Base.metadata.create_all(SQL_ENGINE)

def create_tables_for_tenant(tenant_name: str, declaretiv_metadata: MetaData) -> None:
    """
    创建租户数据库表
    """
    with SQL_ENGINE.connect() as conn:
        # set search_path
        conn.execute(text("SET SESSION search_path TO :tenant"), {"tenant": tenant_name})
        declaretiv_metadata.create_all(conn)
        conn.commit()


def tenent_session(tenant_name: str) -> None:
    """
    创建租户数据库会话
    """
    ss = Session(bind=SQL_ENGINE)
    def __set_local_search_path(session: Session, transaction:SessionTransaction):
        transaction.connection().execute(text("SET LOCAL search_path TO :tenant"),
                                         {"tenant": tenant_name})
    listen(ss, "after_transaction_create", __set_local_search_path)
    return ss