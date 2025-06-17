from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, mapped_column, relationship, Mapped, DeclarativeBase
from sqlalchemy.engine.url import URL
from sqlalchemy import create_engine
from pathlib import Path
from ..constant import SQLLITE_DB_PATH

# declarative base class
class Base(DeclarativeBase):
    pass

class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    upload_time: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    size_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class MarkdownExport(Base):
    __tablename__ = "markdown_exports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    md_uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    file_uuid: Mapped[str] = mapped_column(String(36), ForeignKey("uploaded_files.uuid"), nullable=False)
    create_time: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    config: Mapped[str] = mapped_column(Text, nullable=False)
    
class ContractReviewTask(Base):
    __tablename__ = "contract_review_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    stautus: Mapped[str] = mapped_column(String(10), nullable=False)
    create_time: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=True)

class SuggestionMergeTask(Base):
    __tablename__ = "suggestion_merge_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    stautus: Mapped[str] = mapped_column(String(10), nullable=False)
    create_time: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=True)
    

# create sqllite database at SQLLITE_DB_PATH
sqllite_url  = URL.create(
    drivername="sqlite",
    database=str(SQLLITE_DB_PATH),
)

sqllite_engine = create_engine(sqllite_url)
Base.metadata.create_all(sqllite_engine)
