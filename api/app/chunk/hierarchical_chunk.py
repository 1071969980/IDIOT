
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_orm_models import MarkdownExport, SQL_ENGINE
from .router_declare import router
from .data_model import HierarchicalChunkConfig, HierarchicalChunkResponse, HierarchicalChunk
from .split_factory import split_text
from api.app.data_model import ErrorResponse
from api.s3_FS import upload_object, download_object, CONTRACT_REVIEW_BUCKET
from io import BytesIO

@router.post(
    "/hierarchical",
    description="处理分层文本块请求，支持自定义分隔符和分块策略",
    response_description="返回包含分层文本块的JSON响应",
    responses={
        "404":{"description": "文件不存在",
            "model": ErrorResponse},
        "500": {"description": "服务器内部错误",
            "model": ErrorResponse}
    }
)
async def hierarchical_chunk(request: HierarchicalChunkConfig) -> HierarchicalChunkResponse:
    try:
        # 解析JSON请求体
        config = request
        
        # 查询数据库
        with Session(bind=SQL_ENGINE) as session:
            q = select(MarkdownExport).where(
                MarkdownExport.md_uuid == config.markdown_uuid,
            )
            db_export = session.execute(q).scalar_one_or_none()
            
            if not db_export:
                raise HTTPException(status_code=404, detail="Markdown export not found")

        # 构建文件路径
        file_name = f"{config.markdown_uuid}.md"

        md_obj = BytesIO()
        if download_object(md_obj, CONTRACT_REVIEW_BUCKET, file_name):
            md_content = md_obj.getvalue().decode("utf-8")
        else:
            raise HTTPException(status_code=404, detail="File not found")
        
        # 分割得到父块
        parent_str_list = split_text(md_content, config.parent_split_config)
        # 对父块进行长度限制
        
        chunks = []
        
        for parent_str in parent_str_list:
            # 分割得到子块
            child_str_list = split_text(parent_str, config.child_split_config) if config.child_split_config else []
            chunks.append(HierarchicalChunk(parent=parent_str, children=child_str_list))
        
        return HierarchicalChunkResponse(chunks=chunks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
