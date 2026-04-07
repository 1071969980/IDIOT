"""系统公告读取服务 - 独立 FastAPI 应用

提供系统级、用户级、会话级公告的 HTTP 读取/写入接口。
"""

from api.core.env_config import debug_config

DEBUG = debug_config.api_debug
if DEBUG:
    import debugpy

    DEBUG_PORT = debug_config.api_debug_port
    print(f"Debugger listening on port {DEBUG_PORT}")
    debugpy.listen(("0.0.0.0", DEBUG_PORT))
    debugpy.wait_for_client()

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.redis.distributed_lock import distributed_lock
from api.app.graceful_shutdown import wait_background_task_for_graceful_shutdown
from api.app.system_notification.router_declare import router
from api.logger import init_logger


@distributed_lock("init_notification_db")
async def init_db():
    """初始化系统公告相关数据库表。

    使用分布式锁保护，防止多 worker 重复建表。
    """
    from api.system_notification.sql_stat.system_notification.utils import (
        create_table as ct1,
    )
    from api.system_notification.sql_stat.system_notification_ack.utils import (
        create_table as ct2,
    )
    from api.system_notification.sql_stat.user_notification.utils import (
        create_table as ct3,
    )
    from api.system_notification.sql_stat.session_notification.utils import (
        create_table as ct4,
    )

    await ct1()
    await ct2()
    await ct3()
    await ct4()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing notification database...")
    await init_db()

    print("Starting system notification server...")
    init_logger()

    yield

    await wait_background_task_for_graceful_shutdown()


app = FastAPI(
    title="System Notification",
    description="系统公告读取服务",
    version="1.0.0",
    root_path="/app-notification",
    lifespan=lifespan,
)

# CORS 由 Nginx 统一处理（proxy_cors.inc），应用层不再重复添加

# 注册系统公告路由
app.include_router(router)
