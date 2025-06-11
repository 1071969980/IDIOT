from ..constant import SQLLITE_DB_PATH, FILE_CACHE_DIR, LEGAL_FILE_EXTENSIONS

from uuid import uuid4
import os
from fastapi import APIRouter ,UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path
from typing import Annotated

router = APIRouter(
    prefix="document",
    tags=["document"],
)

@router.post("/upload")
async def upload_large_file(file: Annotated[UploadFile, File()] = ...) -> JSONResponse:
    try:
        file_extension = Path(file.filename).suffix
        if file_extension not in LEGAL_FILE_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Invalid file extension")
        uuid = str(uuid4())
        # 构造文件保存路径
        file_path = FILE_CACHE_DIR / f"{uuid}.{file_extension}"
        
        # 流式写入文件
        with file_path.open("wb") as f:
            # 分块读取并写入（每次处理8MB）
            while chunk := await file.read(8 * 1024 * 1024):
                f.write(chunk)
        
        return JSONResponse(
            status_code=200,
            content={
                "file_id": uuid,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
