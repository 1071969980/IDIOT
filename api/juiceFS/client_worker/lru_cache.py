"""LRU 缓存实现，用于限制 Client 数量"""

from collections import OrderedDict
from typing import Any, Optional


class LRUCache:
    """LRU 缓存，用于限制 Client 数量

    当缓存满时，自动驱逐最久未使用的条目。
    """

    def __init__(self, max_size: int = 20):
        """
        初始化 LRU 缓存

        Args:
            max_size: 最大缓存数量
        """
        self.max_size = max_size
        self._cache: OrderedDict = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值

        Args:
            key: 缓存键

        Returns:
            缓存值，如果不存在返回 None
        """
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, value: Any) -> Optional[str]:
        """
        添加值到缓存

        Args:
            key: 缓存键
            value: 缓存值

        Returns:
            被驱逐的键（如果有），否则返回 None
        """
        evicted = None
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = value
        else:
            if len(self._cache) >= self.max_size:
                evicted, _ = self._cache.popitem(last=False)
            self._cache[key] = value
        return evicted

    def clear(self):
        """清空缓存"""
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, key: str) -> bool:
        return key in self._cache