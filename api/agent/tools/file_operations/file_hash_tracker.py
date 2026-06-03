"""
文件哈希跟踪器

跟踪 Agent 读写的文件内容哈希，用于：
1. 确保 Agent 编辑文件前已读取过该文件
2. 检测文件自上次读取后是否被外部修改
3. 在 Agent 循环中注入变更提醒

数据存储：
- storage_snapshot: 记录 Agent 视角的文件哈希（每次 read/edit 更新）
- Redis: 记录编辑后的文件哈希（仅 edit 后写入，用于检测外部修改）
"""

import time
from uuid import UUID

import xxhash

from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_keys import StorageSnapshotKeys
from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_op import (
    get_branch_storage_snapshot,
    update_branch_storage_snapshot,
)
from api.redis.retry import retry_on_connection_error


class FileHashNotFoundError(Exception):
    """文件未被 read_file 读取过，无法执行编辑操作"""


class FileHashMismatchError(Exception):
    """文件内容自上次读取后已被外部修改"""


class FileHashTracker:
    """跟踪文件内容哈希，支持变更检测和编辑验证。

    哈希记录在 storage_snapshot 的 "file_hashes" 键下，
    格式为 {file_path: {"hash": "xxh64:<hex>", "ts": <unix_timestamp>}}。

    编辑后的哈希同时写入 Redis（TTL 1 天），用于在 Agent 循环中检测外部修改。
    """

    STORAGE_KEY = StorageSnapshotKeys.FILE_HASHES
    MAX_ENTRIES = 200
    REDIS_TTL_SECONDS = 86400  # 1 day

    def __init__(self, session_id: UUID, user_id: UUID, branch_name: str):
        self.session_id = session_id
        self.user_id = user_id
        self.branch_name = branch_name

    @staticmethod
    def compute_hash(content: str) -> str:
        """计算内容的 xxHash 哈希（xxh64, 16位十六进制）。"""
        return "xxh64:" + xxhash.xxh64(content.encode("utf-8")).hexdigest()

    def _redis_key(self, file_path: str) -> str:
        """构建 Redis 键名。"""
        return f"{self.STORAGE_KEY}:user_id:{self.user_id}:file_path:{file_path}"

    async def record_read(self, file_path: str, content: str) -> None:
        """读取后记录哈希到 storage_snapshot（不写 Redis）。

        Agent 的读取操作不写入 Redis，因为读取不应改变 Redis 中的
        "编辑后哈希"状态。Redis 仅在 edit 后更新。
        """
        hash_value = self.compute_hash(content)
        await self._update_snapshot_hash(file_path, hash_value)

    async def verify_before_edit(self, file_path: str, current_content: str) -> None:
        """编辑前验证哈希。

        Raises:
            FileHashNotFoundError: 文件未被 read_file 读取过
            FileHashMismatchError: 文件内容自上次读取后已被修改
        """
        _, snapshot = await get_branch_storage_snapshot(
            session_id=self.session_id,
            user_id=self.user_id,
            branch_name=self.branch_name,
        )
        file_hashes = snapshot.get(self.STORAGE_KEY, {})
        entry = file_hashes.get(file_path)
        stored_hash = entry["hash"] if isinstance(entry, dict) else entry

        if stored_hash is None:
            raise FileHashNotFoundError(
                f"文件 {file_path} 尚未被读取。请先使用 read_file 读取该文件后再编辑。"
            )

        current_hash = self.compute_hash(current_content)
        if current_hash != stored_hash:
            raise FileHashMismatchError(
                f"文件 {file_path} 的内容已发生变化（自上次读取后被修改）。请重新读取该文件后再编辑。"
            )

    async def record_after_edit(self, file_path: str, updated_content: str) -> None:
        """编辑后更新 storage_snapshot 和 Redis。"""
        hash_value = self.compute_hash(updated_content)
        await self._update_snapshot_hash(file_path, hash_value)
        await self._write_to_redis(file_path, hash_value)

    async def check_external_edits(self) -> list[tuple[str, str, str]]:
        """比较 storage_snapshot 与 Redis，返回不一致的文件列表。

        仅检查两个存储都有记录的文件。Redis 无记录的文件（未被 edit 过）
        不视为外部修改。

        Returns:
            [(file_path, snapshot_hash, redis_hash), ...] 不一致的文件列表
        """
        from api.redis.constants import CLIENT

        _, snapshot = await get_branch_storage_snapshot(
            session_id=self.session_id,
            user_id=self.user_id,
            branch_name=self.branch_name,
        )
        file_hashes = snapshot.get(self.STORAGE_KEY, {})

        if not file_hashes:
            return []

        # MGET 批量查询，单次 round-trip
        redis_keys = [self._redis_key(fp) for fp in file_hashes]
        redis_values = await retry_on_connection_error(
            lambda: CLIENT.mget(redis_keys),
            operation_name="file_hash_tracker.check_external_edits",
        )

        mismatches: list[tuple[str, str, str]] = []
        for (file_path, entry), redis_value in zip(file_hashes.items(), redis_values):
            stored_hash = entry["hash"] if isinstance(entry, dict) else entry
            if redis_value is not None and redis_value.decode() != stored_hash:
                mismatches.append((file_path, stored_hash, redis_value.decode()))

        return mismatches

    async def _update_snapshot_hash(self, file_path: str, hash_value: str) -> None:
        """使用 update_branch_storage_snapshot 原子更新单个文件的哈希。

        存储格式为 {file_path: {"hash": "...", "ts": <unix_timestamp>}}。
        超过 MAX_ENTRIES 时按 ts 从旧到新淘汰。
        """
        storage_key = self.STORAGE_KEY
        max_entries = self.MAX_ENTRIES
        now = time.time()

        def _update(snapshot: dict) -> bool:
            file_hashes: dict = snapshot.setdefault(storage_key, {})

            # 更新或插入
            file_hashes[file_path] = {"hash": hash_value, "ts": now}

            # 超出上限时淘汰最旧的条目
            if len(file_hashes) > max_entries:
                sorted_paths = sorted(
                    file_hashes,
                    key=lambda k: file_hashes[k].get("ts", 0) if isinstance(file_hashes[k], dict) else 0,
                )
                for old_path in sorted_paths[: len(file_hashes) - max_entries]:
                    del file_hashes[old_path]

            return True

        await update_branch_storage_snapshot(
            session_id=self.session_id,
            user_id=self.user_id,
            branch_name=self.branch_name,
            update_fn=_update,
        )

    async def _write_to_redis(self, file_path: str, hash_value: str) -> None:
        """写入哈希到 Redis（TTL 1 天），使用 retry_on_connection_error 保证可靠性。"""
        from api.redis.constants import CLIENT

        await retry_on_connection_error(
            lambda: CLIENT.set(
                self._redis_key(file_path), hash_value, ex=self.REDIS_TTL_SECONDS
            ),
            operation_name="file_hash_tracker.write_to_redis",
        )
