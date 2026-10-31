import asyncio
from collections.abc import AsyncGenerator, AsyncIterable
from typing import TypeVar

T = TypeVar("T")

SSE_HEARTBEAT_FRAME = ": heartbeat\n\n"


async def iter_with_heartbeat(
    source: AsyncIterable[T],
    heartbeat_interval: float = 15.0,
) -> AsyncGenerator[T | None, None]:
    """Yield source items, emitting None when no item arrives before the heartbeat interval."""
    iterator = source.__aiter__()
    next_item = asyncio.ensure_future(iterator.__anext__())

    try:
        while True:
            done, _ = await asyncio.wait(
                {next_item},
                timeout=heartbeat_interval,
            )
            if not done:
                yield None
                continue

            try:
                item = next_item.result()
            except StopAsyncIteration:
                return

            next_item = asyncio.ensure_future(iterator.__anext__())
            yield item
    finally:
        if not next_item.done():
            next_item.cancel()
            try:
                await next_item
            except asyncio.CancelledError:
                pass
