"""Redis + PG 双写工具函数。

设计原则：先写 PG（保证持久化），再写 Redis（加速读取），Redis 写入失败只记日志不回滚。

用户级/会话级：双写 + cache-aside 读取。
系统级：cache-aside 读取 + 全局版本号失效机制（详见 redis_ops.py）。
"""

import json
from datetime import datetime
from typing import Awaitable, Callable
from uuid import UUID

import logfire

from api.redis.constants import CLIENT
from api.system_notification.redis_ops import (
    DEFAULT_TTL,
    check_empty_marker,
    delete_notification_from_redis,
    get_cache_version,
    get_system_notification_version,
    hash_is_empty,
    read_notifications_from_redis,
    set_cache_version,
    set_empty_marker,
    write_notification_to_redis,
)
from api.system_notification.types import InternalNotification


def _parse_datetime(value: str | datetime) -> datetime:
    """将字符串或 datetime 统一转为 datetime。"""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _parse_uuid(value: str | UUID) -> UUID:
    """将字符串或 UUID 统一转为 UUID。"""
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _dict_to_internal(d: dict) -> InternalNotification:
    """将 Redis 缓存的 dict 转为 InternalNotification。"""
    return InternalNotification(
        id=_parse_uuid(d["id"]),
        level=d["level"],
        content=d["content"],
        created_at=_parse_datetime(d["created_at"]),
        user_id=_parse_uuid(d["user_id"]) if "user_id" in d and d["user_id"] else None,
        session_id=_parse_uuid(d["session_id"]) if "session_id" in d and d["session_id"] else None,
    )


def _dataclass_to_internal(notif) -> InternalNotification:
    """将 PG 查询的 dataclass 转为 InternalNotification。"""
    return InternalNotification(
        id=notif.id,
        level=notif.level,
        content=notif.content,
        created_at=notif.created_at,
        user_id=getattr(notif, "user_id", None),
        session_id=getattr(notif, "session_id", None),
    )


async def write_notification_with_dual_write(
    stream_key: str,
    db_write_coro: Callable[[], Awaitable],
    notification_data: dict | None = None,
):
    """先写PG再写Redis。PG失败则整体失败；Redis失败仅记日志。

    PG写入成功后，使用返回结果的 ID 作为 Redis 消息的 notification_id。
    db_write_coro 必须返回一个具有 .id 属性的对象（如 dataclass 查询结果）。
    当 notification_data 为 None 时，从 result 对象自动构造完整数据（包含 id、level、content、created_at）。
    """
    with logfire.span("dual_write::write_notification"):
        # 1. 写 PostgreSQL
        result = await db_write_coro()

        # 2. 构造写入 Redis 的完整数据
        redis_data = (
            notification_data
            if notification_data is not None
            else {
                "id": str(result.id),
                "level": result.level,
                "content": result.content,
                "created_at": (
                    result.created_at.isoformat()
                    if hasattr(result, "created_at")
                    else None
                ),
            }
        )

        # 3. 写 Redis（非阻塞错误）
        try:
            await write_notification_to_redis(
                stream_key, str(result.id), redis_data
            )
        except Exception as e:
            logfire.warning(
                "Redis write failed, PG record persisted",
                stream_key=stream_key,
                error=str(e),
            )
        return result


async def ack_with_dual_write(
    stream_key: str,
    ack_db_coro: Callable[[], Awaitable[bool]],
    notification_id: str,
) -> bool:
    """先写PG确认记录，再从Redis删除对应消息。

    ACK 成功后，检查 Hash 是否已空（O(1)），
    若为空则主动设置空结果标记 Key，避免后续读取穿透到 PG。
    """
    with logfire.span("dual_write::ack_notification"):
        success = await ack_db_coro()
        if success:
            try:
                await delete_notification_from_redis(stream_key, notification_id)
                if await hash_is_empty(stream_key):
                    await set_empty_marker(stream_key)
            except Exception as e:
                logfire.warning(
                    "Redis delete failed after PG ack",
                    stream_key=stream_key,
                    error=str(e),
                )
        return success


async def read_with_cache_fallback(
    stream_key: str,
    db_read_coro: Callable[[], Awaitable[list]],
    notification_type: str,
) -> list[InternalNotification]:
    """先读Redis，miss则读PG并回填。

    系统级公告使用全局版本号机制：
    - 比对缓存 _version 与全局版本号，不匹配则视为 cache miss
    - 空 marker 也携带版本号，版本不匹配时 marker 自动失效

    用户级/会话级使用传统 cache-aside：
    - 检查空 marker → 读 Redis → 回源 PG → 回填

    返回值统一为 list[InternalNotification]。
    """
    with logfire.span("dual_write::read_notification", notification_type=notification_type):
        is_system = notification_type == "system"

        # 系统级：获取当前全局版本号
        current_version = None
        if is_system:
            try:
                current_version = await get_system_notification_version()
            except Exception:
                pass

        # 检查空结果标记（系统级带版本号比对）
        try:
            if await check_empty_marker(stream_key, version=current_version):
                return []
        except Exception:
            pass

        # ── 系统级：版本号比对 ──
        if is_system and current_version is not None:
            cached_version = await get_cache_version(stream_key)
            if cached_version == current_version:
                # 版本匹配，信任缓存
                try:
                    cached = await read_notifications_from_redis(stream_key)
                    if cached:
                        return [_dict_to_internal(d) for d in cached]
                except Exception:
                    pass
                # 版本匹配但无公告数据（全部已 ACK），直接返回空
                return []
            # 版本不匹配 → cache miss，回源 PG

        # ── 用户/会话级：传统 Redis 读取 ──
        elif not is_system:
            try:
                cached = await read_notifications_from_redis(stream_key)
                if cached:
                    return [_dict_to_internal(d) for d in cached]
            except Exception as e:
                logfire.warning(
                    "Redis read failed, falling back to PG", error=str(e)
                )

        # 回源 PG
        results = await db_read_coro()

        # PG dataclass → InternalNotification
        if results:
            internal_list = [_dataclass_to_internal(r) for r in results]
            # 构造 Redis 回填用的 dict
            redis_dicts = []
            for n in internal_list:
                item = {
                    "id": str(n.id),
                    "level": n.level,
                    "content": n.content,
                    "created_at": n.created_at.isoformat(),
                }
                if n.user_id is not None:
                    item["user_id"] = str(n.user_id)
                if n.session_id is not None:
                    item["session_id"] = str(n.session_id)
                redis_dicts.append(item)
        else:
            internal_list = []
            redis_dicts = []

        # 回填 Redis（pipeline 批量写入）
        if redis_dicts:
            try:
                async with CLIENT.pipeline() as pipe:
                    for notif_dict in redis_dicts:
                        pipe.hset(
                            stream_key,
                            notif_dict["id"],
                            json.dumps(notif_dict, default=str, ensure_ascii=False),
                        )
                    pipe.expire(stream_key, DEFAULT_TTL)
                    await pipe.execute()
                # 系统级：写入版本号
                if is_system and current_version is not None:
                    await set_cache_version(stream_key, current_version)
            except Exception as e:
                logfire.warning(
                    "Redis backfill failed",
                    stream_key=stream_key,
                    error=str(e),
                )
        else:
            # PG 返回空 → 设置空 marker（系统级带版本号）
            try:
                await set_empty_marker(stream_key, version=current_version)
            except Exception as e:
                logfire.warning(
                    "Failed to set empty marker",
                    stream_key=stream_key,
                    error=str(e),
                )
        return internal_list
