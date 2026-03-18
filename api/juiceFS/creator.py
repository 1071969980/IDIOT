"""JuiceFS 创建器模块

用于初始化给定 user_id 的 JuiceFS 文件系统，包括：
1. 创建 MinIO 存储桶用于存储 JuiceFS 数据分块
2. 创建 PostgreSQL 数据库用于存储 JuiceFS 元数据
3. 使用 juicefs format 命令初始化文件系统
"""

import os
import subprocess

import logfire
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from uuid import UUID

from api.juiceFS.string_utils import StringVarName, get_string_var
from api.logger.logger import log_span
from api.s3_FS import setup_bucket, JUICEFS_S3_CLIENT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY
from api.sql_utils.constant import JUICE_FS_METADATA_ASYNC_SQLENGINE

# FQDN 格式的 JuiceFS PostgreSQL 连接模板
JUICEFS_DB_URL_TEMPLATE = "postgresql+asyncpg://postgres:{password}@juicefs-postgres.idiot-user-space-storage.svc.cluster.local:5432/{db_name}"


def _get_juicefs_postgres_password() -> str:
    """获取 JuiceFS PostgreSQL 密码"""
    return os.environ.get("JUICEFS_POSTGRES_PASSWORD", "juicefs-postgres")


@log_span("创建 MinIO 存储桶", args_captured_as_tags=["user_id"])
async def create_minio_bucket(user_id: UUID | str) -> bool:
    """创建 MinIO 存储桶用于存储 JuiceFS 数据分块"""
    bucket_name = get_string_var(StringVarName.JuiceFS_User_OSS_Bucket_Name, user_id)
    result = setup_bucket(bucket_name, client=JUICEFS_S3_CLIENT)
    if result:
        logfire.info(f"MinIO bucket '{bucket_name}' created successfully")
    else:
        logfire.error(f"Failed to create MinIO bucket '{bucket_name}'")
    return result


@log_span("创建 PostgreSQL 数据库", args_captured_as_tags=["user_id"])
async def create_postgresql_database(user_id: UUID | str) -> bool:
    """创建 PostgreSQL 数据库用于存储 JuiceFS 元数据"""
    db_name = get_string_var(StringVarName.JuiceFS_User_Metadata_DB_NAME, user_id)

    async with JUICE_FS_METADATA_ASYNC_SQLENGINE.connect() as conn:
        # 检查数据库是否已存在
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :db_name"),
            {"db_name": db_name}
        )
        if result.first() is not None:
            logfire.info(f"PostgreSQL database '{db_name}' already exists")
            return True

        # 创建数据库（需要在 autocommit 模式下执行）
        await conn.execute(text("COMMIT"))
        await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        logfire.info(f"PostgreSQL database '{db_name}' created successfully")
        return True


@log_span("创建 JuiceFS 文件系统", args_captured_as_tags=["user_id"])
def create_juicefs_filesystem(user_id: UUID | str) -> bool:
    """使用 juicefs format 命令创建 JuiceFS 文件系统"""
    bucket_url = get_string_var(StringVarName.JuiceFS_User_OSS_Bucket_URL, user_id)
    metadata_db_url = get_string_var(StringVarName.JuiceFS_User_Metadata_DB_URL, user_id)
    meta_name = get_string_var(StringVarName.JuiceFS_Meta_Name, user_id)

    cmd = [
        "juicefs", "format",
        "--storage", "minio",
        "--bucket", bucket_url,
        "--access-key", MINIO_ACCESS_KEY,
        "--secret-key", MINIO_SECRET_KEY,
        metadata_db_url,
        meta_name
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logfire.info(f"JuiceFS filesystem '{meta_name}' created successfully")
        logfire.debug(f"juicefs format output: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        logfire.error(f"Failed to create JuiceFS filesystem: {e.stderr}")
        return False
    except FileNotFoundError:
        logfire.error("juicefs command not found, please ensure JuiceFS is installed")
        return False

@log_span("初始化 JuiceFS 目录", args_captured_as_tags=["user_id"])
async def init_dir_juicefs_for_user(user_id: UUID | str) -> bool:
    """初始化用户 JuiceFS 目录结构

    创建三个初始目录：sys（系统）、pub（公共）、priv（私有）。

    保护机制：这些初始目录在 api.app.user_file_system.data_model 中受到保护，
    通过 DeleteRequest、MoveRequest、CopyRequest 的字段验证器阻止删除、移动或复制覆盖操作。
    """
    metadata_db_url = get_string_var(StringVarName.JuiceFS_User_Metadata_DB_URL, user_id)
    pvc_name = get_string_var(StringVarName.K8S_JuiceFS_User_PVC_Name, user_id)

    try:
        from api.juiceFS.client_worker import get_worker_pool, Operation

        pool = get_worker_pool()

        # 根据 juicefs 动态挂载的说明，用户容器中挂载的目录实际是 juicefs 中的 /{PathPattern}, PathPattern 定义于用户 storage class.
        # 因此需要从python客户端创建目录时需要加上 /{PathPattern} 前缀
        await pool.call(metadata_db_url, Operation.MKDIRS, f"/{pvc_name}/sys")
        await pool.call(metadata_db_url, Operation.MKDIRS, f"/{pvc_name}/pub")
        await pool.call(metadata_db_url, Operation.MKDIRS, f"/{pvc_name}/priv")

        logfire.info("JuiceFS dir initialized for user")
        return True
    except Exception as e:
        logfire.error(f"Failed to initialize JuiceFS dir for user: {e}")
        return False


@log_span("检查 JuiceFS 格式化状态", args_captured_as_tags=["user_id"])
async def check_juicefs_formatted(user_id: UUID | str) -> bool:
    """检查 JuiceFS 是否已经正确格式化

    通过检查用户数据库中是否存在 jfs_ 开头的表来判断。

    Args:
        user_id: 用户ID

    Returns:
        bool: JuiceFS 是否已正确格式化
    """
    db_name = get_string_var(StringVarName.JuiceFS_User_Metadata_DB_NAME, user_id)
    password = _get_juicefs_postgres_password()
    db_url = JUICEFS_DB_URL_TEMPLATE.format(db_name=db_name, password=password)

    # 创建连接到用户数据库的引擎
    user_db_engine = create_async_engine(db_url, future=True)

    try:
        async with user_db_engine.connect() as conn:
            # 查询是否存在 jfs_ 开头的表
            result = await conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name LIKE 'jfs_%'"
                )
            )
            count = result.scalar()

            if count and count > 0:
                logfire.info(f"JuiceFS already formatted, found {count} jfs_ tables")
                return True
            else:
                logfire.info("JuiceFS not formatted, no jfs_ tables found")
                return False
    except Exception as e:
        logfire.error(f"Failed to check JuiceFS format status: {e}")
        return False
    finally:
        await user_db_engine.dispose()


@log_span("为用户创建 JuiceFS 环境", args_captured_as_tags=["user_id"])
async def create_juicefs_for_user(user_id: UUID | str) -> bool:
    """为指定用户创建完整的 JuiceFS 环境

    按顺序执行：
    1. 创建 MinIO 存储桶
    2. 创建 PostgreSQL 数据库
    3. 初始化 JuiceFS 文件系统

    Args:
        user_id: 用户ID

    Returns:
        bool: 所有步骤是否成功完成
    """
    # Step 1: 创建 MinIO 存储桶
    if not await create_minio_bucket(user_id):
        logfire.error("Failed to create MinIO bucket, aborting")
        return False

    # Step 2: 创建 PostgreSQL 数据库
    if not await create_postgresql_database(user_id):
        logfire.error("Failed to create PostgreSQL database, aborting")
        return False

    # Step 3: 初始化 JuiceFS 文件系统
    if not create_juicefs_filesystem(user_id):
        logfire.error("Failed to create JuiceFS filesystem, aborting")
        return False

    if not await init_dir_juicefs_for_user(user_id):
        logfire.error("Failed to initialize JuiceFS dir, aborting")
        return False
    return True