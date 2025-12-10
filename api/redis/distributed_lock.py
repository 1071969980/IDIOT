import asyncio
import time
import uuid
from contextlib import suppress

from .constants import CLIENT


class RedisDistributedLock:
    """
    Redis 分布式锁实现

    基于 SET NX EX 命令实现的分布式锁，支持：
    - 自动续期（看门狗机制）
    - 锁超时自动释放
    - 防止客户端崩溃导致的死锁
    - 可重入（通过唯一标识符）

    使用方式：
        # 方式1：上下文管理器
        async with RedisDistributedLock("my_lock", timeout=30) as lock:
            # 临界区代码
            pass

        # 方式2：手动获取和释放
        lock = RedisDistributedLock("my_lock", timeout=30)
        await lock.acquire()
        try:
            # 临界区代码
            pass
        finally:
            await lock.release()
    """

    def __init__(
        self,
        key: str,
        timeout: float = 30,
        auto_renewal: bool = True,
        renewal_interval: float = 20,
        lock_prefix: str = "distributed_lock:",
    ):
        """
        初始化分布式锁

        Args:
            key: 锁的键名
            timeout: 锁的超时时间（秒）
            auto_renewal: 是否自动续期
            renewal_interval: 续期间隔时间（秒）
            lock_prefix: 锁的键名前缀
        """
        self.key = f"{lock_prefix}{key}"
        self.timeout = int(timeout)
        self.auto_renewal = auto_renewal
        self.renewal_interval = int(renewal_interval)
        self.identifier = str(uuid.uuid4())
        self._acquired = False
        self._renewal_task: asyncio.Task | None = None

    async def __aenter__(self) -> "RedisDistributedLock":
        """异步上下文管理器入口"""
        if not await self.acquire():
            raise RuntimeError(f"Failed to acquire lock: {self.key}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.release()

    async def acquire(self, blocking: bool = True, timeout: float | None = None) -> bool:
        """
        获取锁

        Args:
            blocking: 是否阻塞等待
            timeout: 阻塞超时时间（秒），None表示无限等待

        Returns:
            bool: 是否成功获取锁

        Raises:
            RuntimeError: Redis连接错误
        """
        if self._acquired:
            raise RuntimeError("Lock already acquired")

        start_time = time.time()

        while True:
            try:
                # 使用 SET NX EX 命令原子性地设置锁
                success = await CLIENT.set(
                    self.key,
                    self.identifier,
                    nx=True,
                    ex=self.timeout,
                )

                if success:
                    self._acquired = True

                    # 启动自动续期任务
                    if self.auto_renewal and self.timeout > self.renewal_interval:
                        self._renewal_task = asyncio.create_task(self._renew_lock())

                    return True

            except Exception as e:
                raise RuntimeError(f"Failed to acquire lock: {e}") from e

            # 如果非阻塞模式，直接返回失败
            if not blocking:
                return False

            # 检查是否超时
            if timeout is not None and time.time() - start_time >= timeout:
                return False

            # 短暂等待后重试
            await asyncio.sleep(1)

    async def release(self) -> bool:
        """
        释放锁

        Returns:
            bool: 是否成功释放锁
        """
        if not self._acquired:
            return False

        try:
            # 停止自动续期任务
            if self._renewal_task:
                self._renewal_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._renewal_task
                self._renewal_task = None

            # 使用 Lua 脚本确保只有锁的持有者才能释放锁
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """

            result = await CLIENT.eval(lua_script, 1, self.key, self.identifier)
            self._acquired = False

            return bool(result)

        except Exception as e:
            raise RuntimeError(f"Failed to release lock: {e}") from e

    async def _renew_lock(self) -> None:
        """自动续期锁的看门狗任务"""
        while self._acquired:
            try:
                # 使用 EXPIRE 命令延长锁的过期时间
                lua_script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("expire", KEYS[1], ARGV[2])
                else
                    return 0
                end
                """

                await CLIENT.eval(lua_script, 1, self.key, self.identifier, str(self.timeout))

            except Exception:
                # 续期失败，停止看门狗任务
                break

            # 等待下一次续期
            await asyncio.sleep(self.renewal_interval)

    async def is_locked(self) -> bool:
        """
        检查锁是否被持有

        Returns:
            bool: 锁是否被持有
        """
        try:
            value = await CLIENT.get(self.key)
            return value is not None
        except Exception as e:
            raise RuntimeError(f"Failed to check lock status: {e}") from e

    async def is_own_lock(self) -> bool:
        """
        检查是否是当前客户端持有的锁

        Returns:
            bool: 是否是当前客户端持有的锁
        """
        try:
            value = await CLIENT.get(self.key)
            return value == self.identifier
        except Exception as e:
            raise RuntimeError(f"Failed to check lock ownership: {e}") from e

    def __del__(self):
        """析构函数，确保资源被释放"""
        if hasattr(self, "_acquired") and self._acquired:
            # 在对象被销毁时发出警告，因为正确的释放应该通过 release() 或上下文管理器
            import warnings
            warnings.warn(
                f"Lock '{self.key}' was not properly released. "
                "Consider using async context manager or explicitly call release().",
                ResourceWarning,
            )

class RedLock:
    """
    红锁算法实现，用于在多个 Redis 实例上获取锁，提高分布式环境下的可靠性

    基于官方 RedLock 算法：https://redis.io/topics/distlock
    """

    def __init__(
        self,
        key: str,
        redis_instances=None,
        timeout: float = 30,
        retry_delay: float = 0.1,
        max_retries: int = 3,
        lock_prefix: str = "redlock:",
    ):
        """
        初始化红锁

        Args:
            key: 锁的键名
            redis_instances: Redis 客户端实例列表，默认使用全局 CLIENT
            timeout: 锁的超时时间（秒）
            retry_delay: 重试延迟时间（秒）
            max_retries: 最大重试次数
            lock_prefix: 锁的键名前缀
        """
        self.key = f"{lock_prefix}{key}"
        self.timeout = timeout
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        self.identifier = str(uuid.uuid4())

        # 如果没有提供 Redis 实例，使用全局客户端
        if redis_instances is None:
            self.redis_clients = [CLIENT]
        else:
            self.redis_clients = redis_instances

        self._acquired = False

    async def acquire(self) -> bool:
        """
        获取红锁

        使用红锁算法，需要在大多数 Redis 实例上成功获取锁

        Returns:
            bool: 是否成功获取锁
        """
        if self._acquired:
            raise RuntimeError("Lock already acquired")

        start_time = time.time()
        quorum = len(self.redis_clients) // 2 + 1

        for attempt in range(self.max_retries):
            successful_acquisitions = 0
            acquisition_start = time.time()

            # 尝试在所有 Redis 实例上获取锁
            tasks = []
            for client in self.redis_clients:
                task = asyncio.create_task(
                    self._acquire_from_instance(client),
                )
                tasks.append(task)

            # 等待所有获取操作完成
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 统计成功的获取次数
            for result in results:
                if isinstance(result, bool) and result:
                    successful_acquisitions += 1

            # 检查是否在大多数实例上成功获取锁
            if successful_acquisitions >= quorum:
                # 检查获取锁的总时间是否超过锁的超时时间
                total_time = time.time() - acquisition_start
                if total_time < self.timeout:
                    self._acquired = True
                    return True

            # 释放已经获取的锁
            await self._release_acquired_locks()

            # 如果不是最后一次尝试，等待后重试
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay)

        return False

    async def release(self) -> bool:
        """
        释放红锁

        Returns:
            bool: 是否成功释放锁
        """
        if not self._acquired:
            return False

        try:
            # 在所有 Redis 实例上释放锁
            tasks = []
            for client in self.redis_clients:
                task = asyncio.create_task(
                    self._release_from_instance(client),
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)
            self._acquired = False

            # 只要在一个实例上成功释放即可
            return any(isinstance(result, bool) and result for result in results)

        except Exception as e:
            raise RuntimeError(f"Failed to release redlock: {e}") from e

    async def _acquire_from_instance(self, client) -> bool:
        """在单个 Redis 实例上获取锁"""
        try:
            return await client.set(
                self.key,
                self.identifier,
                nx=True,
                ex=self.timeout,
            )
        except Exception:
            return False

    async def _release_from_instance(self, client) -> bool:
        """在单个 Redis 实例上释放锁"""
        try:
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            result = await client.eval(lua_script, 1, self.key, self.identifier)
            return bool(result)
        except Exception:
            return False

    async def _release_acquired_locks(self) -> None:
        """释放已获取的锁"""
        tasks = []
        for client in self.redis_clients:
            task = asyncio.create_task(
                self._release_from_instance(client),
            )
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)

    async def __aenter__(self) -> "RedLock":
        """异步上下文管理器入口"""
        if not await self.acquire():
            raise RuntimeError(f"Failed to acquire redlock: {self.key}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.release()
