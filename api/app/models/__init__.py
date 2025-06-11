from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, mapped_column, relationship, Mapped, DeclarativeBase
from sqlalchemy import create_engine
from ..constant import SQLLITE_DB_PATH

# declarative base class
class Base(DeclarativeBase):
    pass

class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
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

    # 建立关系
    file = relationship("UploadedFile", back_populates="markdown_exports")

# create sqllite database at SQLLITE_DB_PATH
engine = create_engine("sqlite:///db.sqlite3")
Base.metadata.create_all(engine)
