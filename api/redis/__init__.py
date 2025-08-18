import asyncio
from .constants import CLIENT
from .human_in_loop import HIL_xadd_msg_with_expired, HIL_RedisMsg

async def check_redis_connection():
    try:
        await CLIENT.ping()
    except Exception as e:
        raise RuntimeError(f"Redis connection error: {e}") from e

asyncio.run(check_redis_connection())

async def xadd_msg_with_expired(stream_key: str, msg: bytes, msg_id:str, expired_time:int) -> None:
    await CLIENT.xadd(stream_key, {"msg": msg, "msg_id": msg_id})
    await CLIENT.expire(stream_key, expired_time)