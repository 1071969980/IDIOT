
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_orm_models import MarkdownExport, sqllite_engine
from ..document.markdown import FILE_CACHE_DIR
from . import router
from .data_model import HierarchicalChunkConfig, HierarchicalChunkResponse
from .split_factory import split_text
from api.app.data_model import ErrorResponse


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
        with Session(bind=sqllite_engine) as session:
            q = select(MarkdownExport).where(
                MarkdownExport.md_uuid == config.markdown_uuid,
            )
            db_export = session.execute(q).scalar_one_or_none()
            
            if not db_export:
                raise HTTPException(status_code=404, detail="Markdown export not found")

        # 构建文件路径
        file_path = FILE_CACHE_DIR / f"{config.markdown_uuid}.md"
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Markdown file not found")

        # 读取文件内容
        with open(file_path) as f:
            md_content = f.read()
        
        # 分割得到父块
        parent_str_list = split_text(md_content, config.parent_split_config)
        # 对父块进行长度限制
        
        chunks = []
        
        return JSONResponse(
            status_code=200,
            content={
                     "chunks": chunks,
                     },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
