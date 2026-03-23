"""
用户 Pod 调度器 - 独立 FastAPI 应用

这是一个独立的 FastAPI 应用，用于管理用户 Kubernetes Pod。
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
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.app.graceful_shutdown import wait_background_task_for_graceful_shutdown
from api.app.user_pod_scheduler import router as user_pod_router
from api.logger import init_logger


async def init_db():
    """初始化数据库表"""
    from api.user_pod_scheduler.sql_stat.utils import create_table
    await create_table()
    print("User pod records table initialized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing database...")
    await init_db()

    print("Starting server...")
    init_logger()

    # 启动心跳检查任务
    from api.user_pod_scheduler.heartbeat_checker import start_heartbeat_checker
    checker_task = start_heartbeat_checker()
    print("Heartbeat checker started")

    # code before yield will be executed before the server starts
    yield
    # code after yield will be executed after the server stops
    
    checker_task.cancel()
    await wait_background_task_for_graceful_shutdown()


app = FastAPI(
    title="User Pod Scheduler",
    description="Kubernetes 用户 Pod 调度器",
    version="1.0.0",
    root_path="/api",
    lifespan=lifespan
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(user_pod_router)


if __name__ == "__main__":
    # Run the server
    uvicorn.run(
        "api.app.user_pod_scheduler_app:app",
        host="127.0.0.1",
        port=8001,  # 使用不同端口避免与主应用冲突
        reload=True
    )