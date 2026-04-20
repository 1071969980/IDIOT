from __future__ import annotations

from uuid import UUID


class LockNames:
    """集中管理所有分布式锁的 key 命名

    静态锁名使用类属性，动态锁名使用类方法。
    所有方法/属性返回 str，可直接传给 RedisDistributedLock / distributed_lock。
    """

    # ---- 静态锁名 ----

    INIT_POSTGRES_DB: str = "init_postgres_db"
    INIT_NOTIFICATION_DB: str = "init_notification_db"

    # ---- 动态锁名 ----

    @classmethod
    def hybrid_file_object(cls, s3_key: str) -> str:
        """HybridFileObject 文件操作锁"""
        return f"HybridFileObject:{s3_key}"

    @classmethod
    def user_pod_schedule(cls, user_id: str | UUID) -> str:
        """用户 Pod 调度锁"""
        return f"user_pod_schedule:{user_id}"

    @classmethod
    def u2a_session_storage(cls, session_id: str | UUID) -> str:
        """U2A 会话存储锁"""
        return f"u2a_session_storage:{session_id}"

    @classmethod
    def process_pending_messages_pre_process(
        cls, session_id: str | UUID, branch_name: str
    ) -> str:
        """待处理消息预处理锁"""
        return f"process_pending_messages:pre_process:{session_id}:{branch_name}"

    @classmethod
    def session_agent_config_command(cls, session_id: str | UUID) -> str:
        """会话 Agent 配置命令锁"""
        return f"session_agent_config_command:session_{session_id}"

    @classmethod
    def agent_role_update(cls, user_id: str | UUID, role_name: str) -> str:
        """Agent 角色更新锁"""
        return f"agent-role-update:lock:{user_id}:{role_name}"

    @classmethod
    def task_storage_snapshot(cls, task_id: str | UUID) -> str:
        """任务存储快照锁"""
        return f"task_storage_snapshot:{task_id}"

    @classmethod
    def schedule_pending_task(cls, session_id: str | UUID, branch_name: str) -> str:
        """pending task 调度锁，防止重复调度"""
        return f"schedule_pending_task:{session_id}:{branch_name}"
