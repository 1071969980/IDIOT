# Redis操作与双写工具

## Redis操作工具（redis_ops.py）

文件位置：`api/system_notification/redis_ops.py`

依赖项目中已有的 Redis 客户端（`api/redis/constants.py`）。

**设计说明**：项目已有 `xadd_msg_with_expired`（位于 `api/redis/__init__.py`），但其消息体为单 `bytes` 字段（用于 Human-in-the-Loop 场景）。公告消息需要多字段结构（`notification_id` + `data`），且数据为 `dict` 类型，与现有函数的 `bytes` 接口不兼容，因此独立实现。

```python
import json
import logfire

from api.redis.constants import CLIENT

# Key 命名常量
SYS_NOTIF_PREFIX = "sys_notif:user:"
USER_NOTIF_PREFIX = "user_notif:user:"
SESSION_NOTIF_PREFIX = "session_notif:session:"

# 空结果标记 Key 后缀（缓存穿透防护）
EMPTY_MARKER_SUFFIX = ":empty"

DEFAULT_TTL = 86400 * 7  # 7天


async def write_notification_to_redis(
    stream_key: str,
    notification_id: str,
    data: dict,
    ttl: int = DEFAULT_TTL,
) -> None:
    """写入一条公告到 Redis Stream 并设置过期时间。

    entry ID 由 Redis 自动生成，notification_id（UUID）存储在消息体字段中。
    ACK/DELETE 时通过 find_and_delete_notification 匹配 notification_id 字段定位消息。
    遵循项目已有模式（参见 api/redis/__init__.py 的 xadd_msg_with_expired）。
    """
    fields = {
        "notification_id": notification_id,
        "data": json.dumps(data, default=str, ensure_ascii=False),
    }
    await CLIENT.xadd(stream_key, fields)
    await CLIENT.expire(stream_key, ttl)


async def read_notifications_from_redis(stream_key: str) -> list[dict]:
    """从 Redis Stream 读取所有公告"""
    if not await CLIENT.exists(stream_key):
        return []
    result = await CLIENT.xread({stream_key: "0-0"})
    if not result:
        return []
    notifications = []
    for _key, messages in result:
        for msg_id, fields in messages:
            notif = json.loads(fields[b"data"])
            notif["id"] = (
                fields[b"notification_id"].decode()
                if isinstance(fields[b"notification_id"], bytes)
                else fields[b"notification_id"]
            )
            notifications.append(notif)
    return notifications


async def find_and_delete_notification(
    stream_key: str, notification_id: str
) -> bool:
    """从 Redis Stream 中查找并删除指定 notification_id 的消息。

    遍历 Stream 中的消息，匹配 notification_id 字段后执行 XDEL。
    返回是否成功删除。
    """
    messages = await CLIENT.xrange(stream_key)
    if not messages:
        return False
    for msg_id, fields in messages:
        nid = fields.get(b"notification_id", b"").decode()
        if nid == notification_id:
            await CLIENT.xdel(stream_key, msg_id)
            return True
    return False


async def delete_notification_from_redis(
    stream_key: str, notification_id: str
) -> bool:
    """从 Redis Stream 中删除指定公告（按 notification_id 匹配）。"""
    return await find_and_delete_notification(stream_key, notification_id)


async def set_empty_marker(stream_key: str, ttl: int = DEFAULT_TTL) -> None:
    """设置空结果标记 Key，防止缓存穿透。

    当 PG 查询返回空列表时调用，标记该 Stream 对应的数据为空。
    """
    marker_key = f"{stream_key}{EMPTY_MARKER_SUFFIX}"
    await CLIENT.set(marker_key, "1", ex=ttl)


async def check_empty_marker(stream_key: str) -> bool:
    """检查空结果标记 Key 是否存在。存在则说明 PG 中无未读公告。"""
    marker_key = f"{stream_key}{EMPTY_MARKER_SUFFIX}"
    return await CLIENT.exists(marker_key) > 0


async def invalidate_all_system_notification_caches() -> int:
    """清理所有用户的系统级公告 Redis 缓存。

    在系统级公告创建后调用，确保各用户下次读取时从数据库拉取最新数据。
    同时清理 Stream Key（如 sys_notif:user:{uuid}）和空结果标记 Key（如 sys_notif:user:{uuid}:empty），
    因为两者均匹配 `sys_notif:user:*` 前缀模式，UNLINK 会一并移除。
    使用 SCAN + UNLINK 异步清理，不阻塞主流程。
    返回清理的 Key 数量。
    """
    with logfire.span("redis_ops::invalidate_sys_notif_caches"):
        count = 0
        async for key in CLIENT.scan_iter(match=f"{SYS_NOTIF_PREFIX}*"):
            await CLIENT.unlink(key)
            count += 1
        logfire.info("Invalidated system notification caches", count=count)
        return count
```

## 双写工具（dual_write.py）

文件位置：`api/system_notification/dual_write.py`

本项目目前没有现成的 Redis+PostgreSQL 双写模式，此模块为新建。设计原则：先写 PG（保证持久化），再写 Redis（加速读取），Redis 写入失败只记日志不回滚。

**注意**：本模块仅用于用户级和会话级公告。系统级公告采用"只写 DB + 清缓存"策略，由 `redis_ops.py` 的 `invalidate_all_system_notification_caches` 和 `notification_service.py` 的读取回填逻辑协同完成。

```python
import logfire
from typing import Callable, Awaitable, Any, Protocol, runtime_checkable

from api.system_notification.redis_ops import (
    write_notification_to_redis,
    read_notifications_from_redis,
    delete_notification_from_redis,
    set_empty_marker,
    check_empty_marker,
)


@runtime_checkable
class _HasId(Protocol):
    """约束 db_write_coro 返回值必须具有 .id 属性。"""
    id: Any


async def write_notification_with_dual_write(
    stream_key: str,
    db_write_coro: Callable[[], Awaitable[_HasId]],
    notification_data: dict | None = None,
) -> _HasId:
    """先写PG再写Redis。PG失败则整体失败；Redis失败仅记日志。

    PG写入成功后，使用返回结果的 ID 作为 Redis 消息的 notification_id。
    db_write_coro 必须返回一个具有 .id 属性的对象（如 dataclass 查询结果）。
    当 notification_data 为 None 时，从 result 对象自动构造完整数据（包含 id、level、content、created_at）。
    """
    with logfire.span("dual_write::write_notification"):
        # 1. 写 PostgreSQL
        result = await db_write_coro()

        # 2. 构造写入 Redis 的完整数据
        redis_data = notification_data if notification_data is not None else {
            "id": str(result.id),
            "level": result.level,
            "content": result.content,
            "created_at": result.created_at.isoformat() if hasattr(result, 'created_at') else None,
        }

        # 3. 写 Redis（非阻塞错误）
        try:
            await write_notification_to_redis(
                stream_key, str(result.id), redis_data
            )
        except Exception as e:
            logfire.warning("Redis write failed, PG record persisted",
                            stream_key=stream_key, error=str(e))
        return result


async def ack_with_dual_write(
    stream_key: str,
    ack_db_coro: Callable[[], Awaitable[bool]],
    notification_id: str,
) -> bool:
    """先写PG确认记录，再从Redis删除对应消息。

    PG ACK 为最终一致性保障，即使 Redis 删除失败，
    下次缓存 miss 回填时也会排除已 ACK 的记录。

    ACK 成功后，检查 Redis Stream 是否已空（所有消息已被 XDEL），
    若为空则主动设置空结果标记 Key，避免后续读取穿透到 PG。
    """
    with logfire.span("dual_write::ack_notification"):
        success = await ack_db_coro()
        if success:
            try:
                await delete_notification_from_redis(stream_key, notification_id)
                # ACK 后检查 Stream 是否已空，若为空则设置标记 Key 防止穿透
                remaining = await read_notifications_from_redis(stream_key)
                if not remaining:
                    await set_empty_marker(stream_key)
            except Exception as e:
                logfire.warning("Redis delete failed after PG ack",
                                stream_key=stream_key, error=str(e))
        return success


async def read_with_cache_fallback(
    stream_key: str,
    db_read_coro: Callable[[], Awaitable[list]],
    notification_type: str,
) -> list[dict]:
    """先读Redis，miss则读PG并回填。回填时设置TTL作为兜底。

    空结果处理：PG返回空列表时，设置空结果标记Key防止缓存穿透。
    返回值统一为 list[dict]，无论数据来源是 Redis 还是 PG。
    normalized dict 包含 id、level、content、created_at 字段，
    以及可选的 user_id / session_id 字段（用于权限校验和归属判断）。
    """
    with logfire.span("dual_write::read_notification"):
        # 检查空结果标记（防止缓存穿透）
        try:
            if await check_empty_marker(stream_key):
                return []
        except Exception:
            pass  # 标记检查失败不影响主流程

        try:
            cached = await read_notifications_from_redis(stream_key)
            if cached:
                return cached
        except Exception as e:
            logfire.warning("Redis read failed, falling back to PG",
                            error=str(e))

        # 回退到 PG 读取
        results = await db_read_coro()

        # 将 PG dataclass 结果统一转为 dict，确保与 Redis 路径返回类型一致
        # 包含所有必要字段：id、level、content、created_at 以及可选的 user_id / session_id
        if results:
            normalized = []
            for notif in results:
                item = {
                    "id": str(notif.id),
                    "level": notif.level,
                    "content": notif.content,
                    "created_at": notif.created_at.isoformat(),
                }
                # 保留 user_id / session_id 字段用于权限校验和归属判断
                if hasattr(notif, "user_id") and notif.user_id is not None:
                    item["user_id"] = str(notif.user_id)
                if hasattr(notif, "session_id") and notif.session_id is not None:
                    item["session_id"] = str(notif.session_id)
                normalized.append(item)
        else:
            normalized = []

        # 回填 Redis（使用 normalized dict 列表）
        if normalized:
            try:
                for notif_dict in normalized:
                    await write_notification_to_redis(
                        stream_key, notif_dict["id"], notif_dict
                    )
            except Exception as e:
                logfire.warning("Redis backfill failed",
                                stream_key=stream_key, error=str(e))
        else:
            # PG 返回空列表，设置空结果标记防止缓存穿透
            try:
                await set_empty_marker(stream_key)
            except Exception as e:
                logfire.warning("Failed to set empty marker",
                                stream_key=stream_key, error=str(e))
        return normalized
```
