from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.s3_FS import upload_object, DEFAULT_BUCKET

from ..constant import LEGAL_FILE_EXTENSIONS
from ..db_orm_models import UploadedFile, SQL_ENGINE
from .router_declare import router


class UploadFileReponese(BaseModel):
    file_id: str

@router.post(
    "/upload",
    description="处理大文件上传请求，支持流式上传和文件元信息存储。",
    response_description="返回包含文件唯一ID的JSON响应",
)
async def upload_large_file(file: Annotated[UploadFile, File(description="通过表单上传的文件对象，需符合允许的扩展名格式。")] = ...) -> UploadFileReponese:

    try:
        file_extension = Path(file.filename).suffix
        if file_extension not in LEGAL_FILE_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Invalid file extension")
        uuid = str(uuid4())
        # 构造文件保存路径
        file_name = f"{uuid}{file_extension}"
        
        # 记录开始时间,东八时区
        upload_start_time = datetime.now(tz=timezone(timedelta(hours=8)))
        
        # 流式写入文件并计算大小
        total_size = file.size
        if not upload_object(file.file, DEFAULT_BUCKET, file_name):
            raise HTTPException(status_code=500, detail="Failed to upload file")
        
        # 转换为MB并保留两位小数
        size_mb = round(total_size / (1024 * 1024), 2)
        
        # 创建数据库记录
        db_file = UploadedFile(
            uuid=uuid,
            file_name=file_name,
            original_name=file.filename,
            upload_time=upload_start_time,
            size_mb=size_mb,
        )
        
        # 提交到数据库
        with Session(bind=SQL_ENGINE) as session:
            session.add(db_file)
            session.commit()
        
        return UploadFileReponese(
            file_id=uuid,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
