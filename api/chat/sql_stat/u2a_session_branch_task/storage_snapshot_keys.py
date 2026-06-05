class StorageSnapshotKeys:
    """集中管理 storage_snapshot (JSONB) 的所有顶层 key 名称。

    storage_snapshot 是 u2a_session_tasks 表的 JSONB 字段，
    用于存储任务相关的结构化数据（配置覆写、技能、待办等）。

    所有属性返回 str，可直接用于 dict 的 get/setdefault/[] 操作。
    """

    SESSION_CONFIG_OVERLAY: str = "session_config_overlay"
    LOADED_SKILLS: str = "loaded_skills"
    TODOS: str = "todos"
    SUB_AGENT_ALIASES: str = "sub_agent_aliases"
    SUB_AGENT_NAMES: str = "sub_agent_names"
    FILE_HASHES: str = "file_hashes"
