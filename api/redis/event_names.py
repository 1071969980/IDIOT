from __future__ import annotations

from uuid import UUID


class EventNames:
    """集中管理所有 Redis Event 的 channel 命名

    静态 channel 名使用类属性，动态 channel 名使用类方法。
    所有方法/属性返回 str，可直接传给 RedisEvent / publish_event / subscribe_to_event。
    """

    # ---- 动态 channel 名 ----

    @classmethod
    def session_task_canceling(cls, session_task_id: str | UUID) -> str:
        """会话任务取消事件"""
        return f"session_task_canceling:{session_task_id}"

    @classmethod
    def session_task_completed(cls, session_task_id: str | UUID) -> str:
        """会话任务已完成事件（无论成功、取消还是失败）"""
        return f"session_task_completed:{session_task_id}"

    @classmethod
    def branch_task_started(cls, session_id: str | UUID, branch_name: str) -> str:
        """分支任务开始处理事件"""
        return f"branch_task_started:{session_id}:{branch_name}"

    @classmethod
    def schedule_pending_task_canceled(cls, session_id: str | UUID, branch_name: str) -> str:
        """pending task 调度取消事件"""
        return f"schedule_pending_task_canceled:{session_id}:{branch_name}"

    @classmethod
    def session_events(cls, session_id: str | UUID) -> str:
        """会话级事件流 Pub/Sub 通道"""
        return f"session_events:{session_id}"
