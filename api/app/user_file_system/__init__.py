"""用户文件系统 API 包

文件结构：
- router_declare.py: APIRouter 实例定义
- data_model.py: 数据模型定义
- utils.py: 工具函数（路径验证、PVC 前缀处理等）
- directory_ops.py: 目录操作端点（list_dir, create_dir）
- file_ops.py: 文件操作端点（read_file, write_file, create_file, download_file, upload_file）
- manage_ops.py: 管理操作端点（move_file, copy_file, delete_file）
- query_ops.py: 查询操作端点（check_exists, get_stat）
- endpoints.py: 主入口，导入并注册所有路由
"""

from .endpoints import router

__all__ = ["router"]