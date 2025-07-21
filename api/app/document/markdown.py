from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from api.app.data_model import ErrorResponse
from api.s3_FS import upload_object, download_object, DEFAULT_BUCKET

from ..db_orm_models import MarkdownExport, UploadedFile, SQL_ENGINE
from ..utils import markitdown_app
from .router_declare import router


class ConvertToMarkdownRequest(BaseModel):
    file_id: str
    
class ConvertToMarkdownResponse(BaseModel):
    markdown_id: str
    
@router.post(
    "/markitdown",
    description="将指定文件转换为Markdown格式并存储结果",
    response_description="返回转换后的Markdown文件唯一ID",
    responses={
        "404" : {"description": "文件不存在",
                 "model": ErrorResponse},
        "500" : {"description": "服务器内部错误",
                 "model": ErrorResponse},
    },
)
async def convert_to_markdown(request: ConvertToMarkdownRequest) -> ConvertToMarkdownResponse:
    try:
        # 解析JSON请求体
        file_id = request.file_id

        # 查询数据库
        with Session(bind=SQL_ENGINE) as session:
            q = select(UploadedFile)\
                .where(UploadedFile.uuid == file_id, UploadedFile.is_deleted == False)
            db_file = session.execute(q).scalar_one_or_none()
            
            if not db_file:
                raise HTTPException(status_code=404, detail="File not found")

        # download from s3
        file_obj = BytesIO()
        if not download_object(file_obj, DEFAULT_BUCKET, db_file.file_name):
            raise HTTPException(status_code=500, detail="Failed to download file from S3")

        md_res = markitdown_app.convert_stream(file_obj,
                                                file_extension=db_file.file_name.split(".")[-1])
        
        md_obj = BytesIO(md_res.text_content.encode())
        
        md_uuid = str(uuid4())
        md_file_name = f"{md_uuid}.md"

        if not upload_object(md_obj, DEFAULT_BUCKET, md_file_name):
            raise HTTPException(status_code=500, detail="Failed to upload file")
        
        # 写入数据库记录
        with Session(bind=SQL_ENGINE) as session:
            stmt = insert(MarkdownExport).values(
                md_uuid=md_uuid,
                file_uuid=db_file.uuid,
                create_time=datetime.now(tz=timezone(timedelta(hours=8))),
                config="{}",  # 默认空配置
            )
            session.execute(stmt)
            session.commit()

        return ConvertToMarkdownResponse(
                    markdown_id=md_uuid,
                )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
