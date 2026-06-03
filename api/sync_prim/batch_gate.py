"""集结门 (BatchGate) 同步原语。

允许动态设置任务总数，当所有任务到达后统一放行。
用于 edit_file 多调用场景：同一文件的多个编辑在集结门处等待，
全员到齐后一起进行冲突检测和执行。
"""

import asyncio
from contextvars import ContextVar

# ContextVar 持有 {file_path: BatchGate} 映射
# 由 base_agent._execute_tool_calls 在检测到同文件多 edit 时设置
current_edit_batch_gates: ContextVar[dict[str, "BatchGate"] | None] = ContextVar(
    "current_edit_batch_gates", default=None
)


class BatchGate:
    """允许动态设置任务总数，当所有任务到达后统一放行。"""

    def __init__(self) -> None:
        self._arrived: int = 0
        self._total: int | None = None
        self._finished: bool = False
        self._event: asyncio.Event = asyncio.Event()
        self._lock: asyncio.Lock = asyncio.Lock()

    def set_total(self, total: int) -> None:
        """设置预期任务总数。若已全部到达则立即放行。"""
        self._total = total
        self._finished = True
        if self._total is not None and self._arrived >= self._total:
            self._event.set()

    def give_up(self) -> None:
        """验证失败的协程放弃参与，仅增加计数。"""
        self._arrived += 1
        if self._finished and self._total is not None and self._arrived >= self._total:
            self._event.set()

    async def arrive(self) -> None:
        """任务在集结处调用，阻塞直到所有任务到齐。"""
        async with self._lock:
            self._arrived += 1
            if self._finished and self._total is not None and self._arrived >= self._total:
                self._event.set()
        await self._event.wait()
