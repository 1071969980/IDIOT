"""系统公告 Task Pod 入口

作为一次性 Job 运行，通过 CLI 参数传入公告级别和内容，
创建系统级公告后退出。不使用 FastAPI。

使用示例:
    python -m api.system_notification_task.task_app --level High --content "系统将于今晚22:00维护"
"""

import argparse
import asyncio

import logfire

from api.logger import init_logger
from api.system_notification.sql_stat.system_notification.utils import (
    _SystemNotificationCreate,
    insert_notification,
)
from api.system_notification.redis_ops import invalidate_all_system_notification_caches


async def create_system_notification(
    level: str,
    content: str,
) -> str:
    """创建系统级公告并使缓存失效。

    1. 写入 PG system_notifications 表
    2. 递增全局版本号，使所有用户的系统级公告缓存失效

    返回创建的公告 UUID。
    """
    with logfire.span("system_notification_task::create", level=level):
        result = await insert_notification(
            _SystemNotificationCreate(level=level, content=content)
        )
        logfire.info("System notification created", notification_id=str(result.id))

        # 递增全局版本号，使所有用户缓存失效
        try:
            version = await invalidate_all_system_notification_caches()
            logfire.info("System notification version bumped", version=version)
        except Exception as e:
            logfire.error("Cache invalidation failed", error=str(e))
            # 不回滚 PG 写入，依赖 TTL 兜底

        return str(result.id)


def main():
    init_logger()
    parser = argparse.ArgumentParser(description="创建系统级公告")
    parser.add_argument(
        "--level",
        required=True,
        choices=["Low", "Normal", "High", "Urgent"],
        help="公告级别",
    )
    parser.add_argument("--content", required=True, help="公告内容")
    args = parser.parse_args()

    notification_id = asyncio.run(create_system_notification(args.level, args.content))
    print(f"Created system notification: {notification_id}")


if __name__ == "__main__":
    main()
