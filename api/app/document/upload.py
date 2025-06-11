from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..constant import FILE_CACHE_DIR, LEGAL_FILE_EXTENSIONS
from ..models import UploadedFile, sqllite_engine
from . import router


@router.post("/upload")
async def upload_large_file(file: Annotated[UploadFile, File()] = ...) -> JSONResponse:
    try:
        file_extension = Path(file.filename).suffix
        if file_extension not in LEGAL_FILE_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Invalid file extension")
        uuid = str(uuid4())
        # 构造文件保存路径
        file_name = f"{uuid}.{file_extension}"
        file_path = FILE_CACHE_DIR / file_name
        
        # 记录开始时间
        upload_start_time = datetime.now()
        
        # 流式写入文件并计算大小
        total_size = 0
        with file_path.open("wb") as f:
            # 分块读取并写入（每次处理8MB）
            while chunk := await file.read(8 * 1024 * 1024):
                f.write(chunk)
                total_size += len(chunk)
        
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
        with Session(bind=sqllite_engine) as session:
            session.add(db_file)
            session.commit()
        
        return JSONResponse(
            status_code=200,
            content={
                "file_id": uuid,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
