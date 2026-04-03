"""Redis Hash 读写操作 + 系统级公告版本号缓存失效。

使用 Redis Hash 存储公告缓存，notification_id 作为 field，
JSON 数据作为 value。

系统级公告缓存失效采用全局版本号机制：
- 创建系统公告时 INCR 全局版本号（O(1)），不再 SCAN 全量删除
- 读取时比对缓存内的 _version 与全局版本号，不匹配则回源 PG
- 空 marker 也携带版本号，新公告创建后旧 marker 自动失效
"""

import json

import logfire

from api.redis.constants import CLIENT

# Key 命名常量
SYS_NOTIF_PREFIX = "sys_notif:user:"
USER_NOTIF_PREFIX = "user_notif:user:"
SESSION_NOTIF_PREFIX = "session_notif:session:"

# 系统公告全局版本号 Key
SYS_NOTIF_VERSION_KEY = "sys_notif:version"

# 空 marker 中存储版本号的分隔符
EMPTY_MARKER_SUFFIX = ":empty"

# Hash 内版本号字段名（元数据，非公告数据）
VERSION_FIELD = "_version"

DEFAULT_TTL = 86400 * 7  # 7天


# ── 系统公告版本号操作 ──


async def get_system_notification_version() -> int:
    """获取当前系统公告全局版本号。"""
    val = await CLIENT.get(SYS_NOTIF_VERSION_KEY)
    return int(val) if val else 0


async def bump_system_notification_version() -> int:
    """递增系统公告全局版本号，返回新版本号。"""
    return await CLIENT.incr(SYS_NOTIF_VERSION_KEY)


# ── Hash 元数据操作 ──


async def set_cache_version(hash_key: str, version: int) -> None:
    """将当前版本号写入 Hash 的 _version 字段。"""
    await CLIENT.hset(hash_key, VERSION_FIELD, str(version))


async def get_cache_version(hash_key: str) -> int | None:
    """读取 Hash 中缓存的版本号。Hash 不存在或无 _version 字段返回 None。"""
    val = await CLIENT.hget(hash_key, VERSION_FIELD)
    if val is None:
        return None
    return int(val)


# ── 通用 Hash 读写 ──


async def write_notification_to_redis(
    hash_key: str,
    notification_id: str,
    data: dict,
    ttl: int = DEFAULT_TTL,
) -> None:
    """写入一条公告到 Redis Hash 并刷新过期时间。

    notification_id 作为 Hash field，JSON 数据作为 value。
    """
    await CLIENT.hset(hash_key, notification_id, json.dumps(data, default=str, ensure_ascii=False))
    await CLIENT.expire(hash_key, ttl)


async def read_notifications_from_redis(hash_key: str) -> list[dict]:
    """从 Redis Hash 读取所有公告（自动跳过 _version 元数据字段）。"""
    if not await CLIENT.exists(hash_key):
        return []
    raw = await CLIENT.hgetall(hash_key)
    if not raw:
        return []
    notifications = []
    for field, value in raw.items():
        if isinstance(field, bytes):
            field = field.decode()
        if field == VERSION_FIELD:
            continue
        if isinstance(value, bytes):
            value = value.decode()
        notifications.append(json.loads(value))
    return notifications


async def delete_notification_from_redis(
    hash_key: str, notification_id: str
) -> bool:
    """从 Redis Hash 中删除指定公告。O(1) 直接按 field 删除。"""
    return await CLIENT.hdel(hash_key, notification_id) > 0


async def hash_is_empty(hash_key: str) -> bool:
    """检查 Hash 是否已空（O(1)），排除 _version 元数据字段。"""
    length = await CLIENT.hlen(hash_key)
    if length == 0:
        return True
    if length == 1:
        return await CLIENT.hexists(hash_key, VERSION_FIELD)
    return False


# ── 空 marker（带版本号感知）──


async def set_empty_marker(
    hash_key: str, ttl: int = DEFAULT_TTL, version: int | None = None
) -> None:
    """设置空结果标记 Key，防止缓存穿透。

    系统级公告传入 version，marker 值为版本号字符串。
    用户/会话级不传 version，marker 值为 "1"（兼容旧逻辑）。
    """
    marker_key = f"{hash_key}{EMPTY_MARKER_SUFFIX}"
    value = str(version) if version is not None else "1"
    await CLIENT.set(marker_key, value, ex=ttl)


async def check_empty_marker(
    hash_key: str, version: int | None = None
) -> bool:
    """检查空结果标记 Key。

    系统级公告传入当前 version，与 marker 中存储的版本号比对，
    版本不匹配说明有新公告，marker 失效，返回 False。
    用户/会话级不传 version，仅检查 key 是否存在。
    """
    marker_key = f"{hash_key}{EMPTY_MARKER_SUFFIX}"
    if version is not None:
        val = await CLIENT.get(marker_key)
        if val is None:
            return False
        try:
            return int(val) == version
        except (ValueError, TypeError):
            return True  # 旧格式 marker（值为 "1"），视为有效
    return await CLIENT.exists(marker_key) > 0


# ── 缓存失效（版本号方案）──


async def invalidate_all_system_notification_caches() -> int:
    """递增系统公告全局版本号，使所有用户缓存失效。

    O(1) 操作，替代原来的 SCAN + UNLINK 全量删除。
    返回新版本号。
    """
    with logfire.span("redis_ops::invalidate_sys_notif_caches"):
        new_version = await bump_system_notification_version()
        logfire.info("Bumped system notification version", version=new_version)
        return new_version
