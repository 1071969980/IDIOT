import asyncio
from .constants import CLIENT
from .human_in_loop import HIL_xadd_msg_with_expired, HIL_RedisMsg

async def check_redis_connection():
    try:
        await CLIENT.ping()
    except Exception as e:
        raise ValueError(f"Redis connection error: {e}") from e

    try:
        # Try to get the running loop
        loop = asyncio.get_running_loop()
        # If we get here, there's already a running loop
        result = loop.run_until_complete(check_redis_connection())
        print(result)
    except RuntimeError:
        # No running loop, so we can use asyncio.run()
        result = asyncio.run(check_redis_connection())
        print(result)

async def xadd_msg_with_expired(stream_key: str, msg: bytes, msg_id:str, expired_time:int) -> None:
    await CLIENT.xadd(stream_key, {"msg": msg, "msg_id": msg_id})
    await CLIENT.expire(stream_key, expired_time)