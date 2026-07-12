"""
JuiceFS SDK 存储后端实现

通过 JuiceFSWorkerPool 直接操作 JuiceFS 文件系统，实现多租户文件操作。
使用 user_id 派生 meta_url 和 pvc_name，确保租户隔离。
"""

import asyncio
import stat
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID

import logfire

from .base import FileOperationsStorageBackend, DirectoryItem, OperationResult
from ..config_scope_data_model import FileOpsToolScope
from api.juiceFS.client_worker import Operation, get_worker_pool
from api.juiceFS.client_worker.models import FileInfo
from api.juiceFS.path_utils import get_meta_url, get_pvc_name, validate_and_build_path
from api.user_pod_scheduler.constants import JUICEFS_MOUNT_PATH
from api.agent.tools.type import UserToolCallingPermissionRole


def _batch_sort_key(item: tuple) -> tuple[int, int]:
    """批次编辑排序键。replace_text 排最后 (group=1)，其余按 start_line 降序 (group=0, -line)。"""
    from ..edit_file.types import EditOp
    action = item[0]
    if action.op == EditOp.REPLACE_TEXT:
        return (1, 0)
    line = action.start_line or 0
    return (0, -line)


class JuiceFSSdkBackend(FileOperationsStorageBackend):
    """
    JuiceFS SDK 存储后端

    通过 JuiceFSWorkerPool 直接操作 JuiceFS 文件系统。
    使用 user_id 派生 meta_url，实现多租户隔离。

    Attributes:
        meta_url: JuiceFS 元数据连接 URL
        pvc_name: 用户 PVC 名称（用于路径前缀）
    """

    def __init__(self, session_id: UUID, scope: FileOpsToolScope):
        """
        初始化 JuiceFS SDK 存储后端

        Args:
            session_id: 会话 ID
            scope: 文件操作作用域配置
        """
        super().__init__(session_id, scope.user_id_for_scope)

        self.scope = scope
        self.meta_url = get_meta_url(str(scope.user_id_for_scope))
        self.pvc_name = get_pvc_name(str(scope.user_id_for_scope))
        self._pool = None
        self._batch_edition_queue: dict[str, list[tuple]] = {}

        for rel_dir in scope.white_list:
            if rel_dir.is_absolute():
                raise ValueError("white_list paths must be relative")
        for rel_dir in scope.black_list:
            if rel_dir.is_absolute():
                raise ValueError("black_list paths must be relative")

    @property
    def pool(self):
        """
        延迟获取全局 JuiceFSWorkerPool 实例

        Returns:
            JuiceFSWorkerPool: 全局工作进程池实例
        """
        if self._pool is None:
            self._pool = get_worker_pool()
        return self._pool

    def _check_work_dir_access(self, safe_path: str) -> None:
        """
        验证路径是否在允许的工作目录范围内（W/B + Role 组合逻辑）。

        逻辑顺序：
        1. VISITOR 角色拒绝任何包含以 '.' 开头路径组件的路径
        2. 黑名单检查：路径在任何 B 目录下则拒绝
        3. 白名单检查：W 为空则允许，否则路径须在某个 W 目录下

        Args:
            safe_path: 已验证的安全路径，格式为 /{pvc_name}/...

        Raises:
            ValueError: 路径被拒绝
        """
        pvc_prefix = PurePosixPath(f"/{self.pvc_name}")
        rel_path = PurePosixPath(safe_path).relative_to(pvc_prefix)
        scope = self.scope

        # VISITOR 隐藏路径检查
        if scope.role == UserToolCallingPermissionRole.VISITOR:
            for part in rel_path.parts:
                if part.startswith('.'):
                    raise ValueError(f"VISITOR 角色不允许访问隐藏路径: {safe_path}")

        # 黑名单检查
        for bl_dir in scope.black_list:
            bl_abs = pvc_prefix / bl_dir
            if PurePosixPath(safe_path).is_relative_to(bl_abs):
                raise ValueError(f"路径在黑名单目录范围内: {safe_path}")

        # 白名单检查
        if not scope.white_list:
            return

        for wl_dir in scope.white_list:
            wl_abs = pvc_prefix / wl_dir
            if PurePosixPath(safe_path).is_relative_to(wl_abs):
                return

        work_dirs_str = ", ".join(
            str(PurePosixPath(JUICEFS_MOUNT_PATH) / rel_dir)
            for rel_dir in scope.white_list
        )
        raise ValueError(f"路径不在允许的工作目录范围内，允许的目录: {work_dirs_str}")

    def _resolve_path(self, file_path: str) -> str:
        """
        构建安全的 JuiceFS 路径并验证工作目录范围

        要求 file_path 为以 JUICEFS_MOUNT_PATH 开头的绝对路径，
        验证后剥离前缀转为相对路径，再传入 validate_and_build_path。

        Args:
            file_path: 以 JUICEFS_MOUNT_PATH 开头的绝对路径

        Returns:
            完整的安全路径，格式为 /{pvc_name}/...

        Raises:
            ValueError: 路径非绝对路径、不以 JUICEFS_MOUNT_PATH 开头、
                       包含非法字符或不在工作目录范围内
        """
        file_path = file_path.strip()

        if not PurePosixPath(file_path).is_absolute():
            raise ValueError(
                f"路径必须为绝对路径，当前为相对路径：{file_path}"
            )

        if not PurePosixPath(file_path).is_relative_to(JUICEFS_MOUNT_PATH):
            raise ValueError(
                f"路径必须以 {JUICEFS_MOUNT_PATH} 开头，当前路径：{file_path}"
            )

        # 剥离 JUICEFS_MOUNT_PATH 前缀，得到相对路径
        rel_path = str(PurePosixPath(file_path).relative_to(JUICEFS_MOUNT_PATH))

        safe_path = validate_and_build_path(rel_path, self.pvc_name)
        self._check_work_dir_access(safe_path)
        return safe_path

    # ========== 读取操作 ==========

    async def read_file(
        self,
        file_path: str,
        offset: int | None = None,
        limit: int | None = None,
        *,
        record_hash: bool = False,
        cancel_event: asyncio.Event | None = None,
    ) -> tuple[str, int, int]:
        """
        读取文件内容

        Args:
            file_path: 文件路径
            offset: 起始行偏移（从0开始）
            limit: 最大读取行数
            cancel_event: 取消事件，设置后可中断等待

        Returns:
            (content, first_line_number, total_lines)

        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 无权限访问
            ValueError: 路径无效
        """
        safe_path = self._resolve_path(file_path)

        with logfire.span("JuiceFSSdkBackend::read_file", path=safe_path):
            result = await self.pool.call(
                self.meta_url, Operation.READ, safe_path,
                cancel_event=cancel_event,
            )

            # bytes -> str
            try:
                content = result.content.decode('utf-8-sig')
            except UnicodeDecodeError as e:
                raise ValueError(f"文件编码错误，无法解码为 UTF-8: {e}")

            # 哈希记录：对完整文件内容计算哈希（不受 offset/limit 影响）
            if record_hash and self.hash_tracker is not None:
                try:
                    await self.hash_tracker.record_read(file_path, content)
                except Exception:
                    pass  # 哈希记录失败不阻塞读取操作

            lines = content.split('\n')
            total_lines = len(lines)

            # 处理空文件
            if total_lines == 1 and lines[0] == '':
                return ("", 1, 0)

            # 计算起始行
            start = 0 if offset is None else max(0, offset)
            if start >= total_lines:
                return ("", start + 1, total_lines)

            # 计算结束行
            end = total_lines if limit is None else min(total_lines, start + limit)
            selected_lines = lines[start:end]

            return ('\n'.join(selected_lines), start + 1, total_lines)

    # ========== 写入操作 ==========

    async def _write_raw(
        self, file_path: str, content: str,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """直接写入 JuiceFS，不做模式检查或哈希跟踪。供 edit 操作的内部写回使用。"""
        safe_path = self._resolve_path(file_path)
        data = content.encode('utf-8')
        await self.pool.call(
            self.meta_url, Operation.WRITE, safe_path, data,
            cancel_event=cancel_event,
        )

    async def write_file(
        self,
        file_path: str,
        content: str,
        mode: Literal["create", "overwrite"] = "create",
        cancel_event: asyncio.Event | None = None,
    ) -> bool:
        """
        写入文件内容

        Args:
            file_path: 文件路径
            content: 文件内容
            mode: 写入模式
            cancel_event: 取消事件，设置后可中断等待

        Returns:
            True 如果成功

        Raises:
            FileExistsError: 文件已存在且 mode="create"
            PermissionError: 无权限写入
            ValueError: 路径无效
        """
        # 检查文件是否存在（仅 create 模式）
        if mode == "create":
            exists = await self.file_exists(file_path, cancel_event=cancel_event)
            if exists:
                raise FileExistsError(f"文件已存在：{file_path}")

        with logfire.span("JuiceFSSdkBackend::write_file", path=file_path):
            await self._write_raw(file_path, content, cancel_event=cancel_event)

        # 写入成功后记录哈希
        if self.hash_tracker is not None:
            try:
                await self.hash_tracker.record_after_edit(file_path, content)
            except Exception:
                pass

        return True

    # ========== 编辑操作 ==========

    async def edit_file(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        cancel_event: asyncio.Event | None = None,
    ) -> tuple[bool, int, str]:
        """
        编辑文件内容，替换指定字符串

        Args:
            file_path: 文件路径
            old_string: 要替换的字符串
            new_string: 替换后的字符串
            replace_all: 是否替换所有匹配项
            cancel_event: 取消事件，设置后可中断等待

        Returns:
            (success, replace_count, updated_content)

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: old_string 不存在或重复出现且 replace_all=False
        """
        # 读取现有内容
        content, _, _ = await self.read_file(file_path, cancel_event=cancel_event)

        # 哈希验证：确保编辑前已读取且文件未被外部修改
        if self.hash_tracker is not None:
            await self.hash_tracker.verify_before_edit(file_path, content)

        # 检查匹配
        count = content.count(old_string)
        if count == 0:
            raise ValueError(f"未找到要替换的内容：{old_string}")
        if count > 1 and not replace_all:
            raise ValueError(f"内容重复出现 {count} 次，请设置 replace_all=true 或指定更精确的内容")

        # 执行替换
        if replace_all:
            updated = content.replace(old_string, new_string)
        else:
            updated = content.replace(old_string, new_string, 1)

        # 写回文件
        await self._write_raw(file_path, updated, cancel_event=cancel_event)

        # 哈希更新：编辑成功后同步 storage_snapshot 和 Redis
        if self.hash_tracker is not None:
            try:
                await self.hash_tracker.record_after_edit(file_path, updated)
            except Exception:
                pass  # 哈希更新失败不影响编辑结果

        return (True, count, updated)

    # ========== 编辑操作 V2 (锚点驱动) ==========

    def register_batch_edition(
        self,
        action,
        event: asyncio.Event,
        batch_id: str,
    ) -> str:
        """注册一个编辑动作到批次队列（同步方法）。

        Args:
            action: EditAction 编辑动作
            event: 完成事件，执行完毕后 set
            batch_id: 批次 ID（即 file_path）

        Returns:
            action_id (UUID)
        """
        from uuid import uuid4
        action_id = str(uuid4())
        queue = self._batch_edition_queue.setdefault(batch_id, [])
        queue.append((action, event, action_id))
        queue.sort(key=_batch_sort_key)
        return action_id

    async def apply_batch_edition_approval(self, batch_id: str, action_id: str) -> None:
        """等待批次中前一个动作完成。

        在已排序的队列中找到当前 action_id，等待前一个元素的 event。
        如果没有前一个元素（队首），立即返回。
        """
        queue = self._batch_edition_queue.get(batch_id, [])
        for i, (_, _, aid) in enumerate(queue):
            if aid == action_id:
                if i > 0:
                    await queue[i - 1][1].wait()
                return

    def _cleanup_batch_queue(self, batch_id: str) -> None:
        """清理已完成的批次。"""
        if batch_id in self._batch_edition_queue:
            all_set = all(event.is_set() for _, event, _ in
                          self._batch_edition_queue[batch_id])
            if all_set:
                del self._batch_edition_queue[batch_id]

    async def edit_file_v2(
        self,
        file_path: str,
        edit_action,
        cancel_event: asyncio.Event | None = None,
    ):
        """锚点驱动的编辑，并行批次流水线。"""
        from api.sync_prim.batch_gate import current_edit_batch_gates

        gates = current_edit_batch_gates.get(None)
        gate = gates.get(file_path) if gates else None

        # ---- 步骤 2: 读取文件 + 验证 ----
        raw_content = await self._read_raw(file_path, cancel_event=cancel_event)
        content, original_line_ending = self._normalize(raw_content)
        lines = content.split('\n')

        try:
            if self.hash_tracker is not None:
                await self.hash_tracker.verify_before_edit(file_path, content)
            self._verify_anchors(lines, [edit_action])
        except Exception:
            if gate is not None:
                gate.give_up()
            raise

        # ---- 步骤 3: 注册批次编辑 ----
        event = asyncio.Event()
        action_id = self.register_batch_edition(edit_action, event, file_path)

        # ---- 步骤 4: 集结门 ----
        if gate is not None:
            await gate.arrive()

        # ---- 步骤 5-8: 执行 ----
        try:
            # 步骤 5: 等待前一个动作完成
            await self.apply_batch_edition_approval(file_path, action_id)

            # 步骤 6: 重新读取文件 + 验证锚点
            raw_content = await self._read_raw(file_path, cancel_event=cancel_event)
            content, original_line_ending = self._normalize(raw_content)
            result_lines = content.split('\n')
            self._verify_anchors(result_lines, [edit_action])

            # 步骤 7: 执行修改
            affected_start, affected_end = self._apply_action(result_lines, edit_action)
            anchor_output = self._build_anchor_output(
                result_lines, affected_start, affected_end
            )

            # 写回 + 哈希更新
            updated_content = original_line_ending.join(result_lines)
            await self._write_raw(file_path, updated_content, cancel_event=cancel_event)
            if self.hash_tracker is not None:
                try:
                    await self.hash_tracker.record_after_edit(file_path, updated_content)
                except Exception:
                    pass
        finally:
            # 步骤 8: 保证 event 被 set（即使执行失败也不死锁后续动作）
            event.set()

        # 清理队列
        self._cleanup_batch_queue(file_path)

        return anchor_output

    async def _read_raw(
        self, file_path: str, cancel_event: asyncio.Event | None = None
    ) -> str:
        """读取文件原始内容（不做行拆分）。"""
        safe_path = self._resolve_path(file_path)

        with logfire.span("JuiceFSSdkBackend::_read_raw", path=safe_path):
            result = await self.pool.call(
                self.meta_url, Operation.READ, safe_path,
                cancel_event=cancel_event,
            )

            try:
                return result.content.decode('utf-8-sig')
            except UnicodeDecodeError as e:
                raise ValueError(f"文件编码错误，无法解码为 UTF-8: {e}")

    @staticmethod
    def _normalize(content: str) -> tuple[str, str]:
        """规范化文件内容: 检测换行符风格、统一为 LF。

        BOM 已在 _read_raw 中通过 utf-8-sig 编码自动剥离。

        Returns:
            (normalized_content, original_line_ending) — LF 统一后的内容和原始换行符
        """
        # 检测换行符风格
        original_line_ending = '\r\n' if '\r\n' in content else '\n'

        # 统一为 LF
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        return content, original_line_ending

    @staticmethod
    def _verify_anchors(lines: list[str], actions: list) -> None:
        """验证所有 action 的锚点哈希是否匹配当前文件内容。"""
        from ..edit_file.types import EditOp
        from ..line_hash import compute_line_hash

        for action in actions:
            pos_hash = action.pos_hash
            end_hash = action.end_hash

            # replace_text 无锚点
            if action.op == EditOp.REPLACE_TEXT:
                continue

            # 验证 pos 锚点
            if action.start_line is not None and pos_hash is not None:
                if action.start_line < 1 or action.start_line > len(lines):
                    raise ValueError(
                        f"锚点行号 {action.start_line} 超出文件范围 (1-{len(lines)})"
                    )
                actual_hash = compute_line_hash(lines[action.start_line - 1])
                if actual_hash != pos_hash:
                    line_content = lines[action.start_line - 1]
                    if len(line_content) > 60:
                        line_content = line_content[:60] + "..."
                    raise ValueError(
                        f"锚点不匹配: 第 {action.start_line} 行哈希期望 {pos_hash}，"
                        f"实际 {actual_hash}。当前内容: {line_content}\n"
                        f"请重新读取文件获取最新内容。"
                    )

            # 验证 end 锚点
            if action.end_line is not None and end_hash is not None:
                if action.end_line < 1 or action.end_line > len(lines):
                    raise ValueError(
                        f"end 行号 {action.end_line} 超出文件范围 (1-{len(lines)})"
                    )
                actual_hash = compute_line_hash(lines[action.end_line - 1])
                if actual_hash != end_hash:
                    line_content = lines[action.end_line - 1]
                    if len(line_content) > 60:
                        line_content = line_content[:60] + "..."
                    raise ValueError(
                        f"锚点不匹配: 第 {action.end_line} 行哈希期望 {end_hash}，"
                        f"实际 {actual_hash}。当前内容: {line_content}\n"
                        f"请重新读取文件获取最新内容。"
                    )

    @staticmethod
    def _apply_action(result_lines: list[str], action) -> tuple[int, int]:
        """应用单个编辑动作到 result_lines (原地修改)。

        Returns:
            (affected_start, affected_end) 1-based, 变更后的行范围
        """
        from ..edit_file.types import EditOp

        if action.op == EditOp.REPLACE:
            start = action.start_line - 1  # 0-based
            end = action.end_line if action.end_line else action.start_line
            end_0 = end  # 0-based exclusive = end (1-based inclusive)
            result_lines[start:end_0] = action.new_lines
            return (action.start_line, action.start_line + len(action.new_lines) - 1)

        elif action.op == EditOp.APPEND:
            if action.start_line is not None:
                insert_at = action.start_line  # 0-based: after start_line
            else:
                insert_at = len(result_lines)  # EOF
            n = len(action.new_lines)
            result_lines[insert_at:insert_at] = action.new_lines
            first_new = insert_at + 1  # 1-based
            return (first_new, first_new + n - 1)

        elif action.op == EditOp.PREPEND:
            if action.start_line is not None:
                insert_at = action.start_line - 1  # 0-based: before start_line
            else:
                insert_at = 0  # BOF
            n = len(action.new_lines)
            result_lines[insert_at:insert_at] = action.new_lines
            first_new = insert_at + 1  # 1-based
            return (first_new, first_new + n - 1)

        elif action.op == EditOp.REPLACE_TEXT:
            # 在拼接内容上替换，然后重新拆行
            content = '\n'.join(result_lines)
            old_text = action.old_text
            new_text = action.new_text

            count = content.count(old_text)
            if count == 0:
                raise ValueError(f"未找到要替换的内容")
            if count > 1 and not action.replace_all:
                raise ValueError(f"内容重复出现 {count} 次，请设置 replace_all=true 或指定更精确的内容")

            if action.replace_all:
                new_content = content.replace(old_text, new_text)
            else:
                new_content = content.replace(old_text, new_text, 1)

            # 找到首个变更的位置来计算受影响范围
            idx = content.find(old_text)
            before_lines = content[:idx].count('\n') + 1
            old_end_lines = content[:idx + len(old_text)].count('\n') + 1
            new_after_lines = new_content[:idx + len(new_text)].count('\n') + 1

            result_lines[:] = new_content.split('\n')

            affected_start = before_lines
            affected_end = max(old_end_lines, new_after_lines)
            return (affected_start, min(affected_end, len(result_lines)))

        return (1, 1)

    @staticmethod
    def _build_anchor_output(
        result_lines: list[str],
        affected_start: int,
        affected_end: int,
    ):
        """构建 EditAnchorOutput。变更区域 ±2 行上下文。"""
        from ..edit_file.types import EditAnchorOutput
        from ..line_hash import compute_line_hash

        total_lines = len(result_lines)
        context_start = max(1, affected_start - 2)
        context_end = min(total_lines, affected_end + 2)
        width = len(str(total_lines))

        total_affected = affected_end - affected_start + 1

        if total_affected > 20:
            # 仅显示前 6 行和后 6 行
            first_6 = range(context_start, min(context_start + 6, context_end + 1))
            last_6 = range(max(context_end - 5, context_start + 6), context_end + 1)
            selected_line_nums = list(first_6) + list(last_6)
        else:
            selected_line_nums = list(range(context_start, context_end + 1))

        formatted_lines = []
        for line_num in selected_line_nums:
            line_content = result_lines[line_num - 1]
            if len(line_content) > 1000:
                line_content = line_content[:1000] + "... [line be truncated]"
            hash_str = compute_line_hash(line_content)
            formatted_lines.append(f"{str(line_num).rjust(width)}#{hash_str}:{line_content}")

        output = EditAnchorOutput(
            start_line=affected_start,
            end_line=affected_end,
            formatted_lines=formatted_lines,
            total_affected=total_affected,
        )
        return output

    # ========== 辅助方法 ==========

    async def file_exists(
        self, file_path: str,
        cancel_event: asyncio.Event | None = None,
    ) -> bool:
        """
        检查文件是否存在

        Args:
            file_path: 文件路径
            cancel_event: 取消事件，设置后可中断等待

        Returns:
            True 如果存在
        """
        try:
            safe_path = self._resolve_path(file_path)
        except ValueError:
            return False

        result = await self.pool.call(
            self.meta_url, Operation.EXISTS, safe_path,
            cancel_event=cancel_event,
        )
        return result.exists

    async def get_item_type(
        self, path: str,
        cancel_event: asyncio.Event | None = None,
    ) -> Literal["file", "directory"] | None:
        """
        获取路径对应的项类型

        Args:
            path: 路径
            cancel_event: 取消事件，设置后可中断等待

        Returns:
            "file", "directory" 或 None（不存在）
        """
        try:
            safe_path = self._resolve_path(path)
        except ValueError:
            return None

        try:
            # 直接调用 STAT 获取状态，避免重复远程调用
            stat_result = await self.pool.call(
                self.meta_url, Operation.STAT, safe_path,
                cancel_event=cancel_event,
            )
            if stat.S_ISDIR(stat_result.stat_info.st_mode):
                return "directory"
            return "file"
        except Exception:
            # 文件不存在或其他错误
            return None

    # ========== 列表操作 ==========

    async def list_directory(
        self, directory_path: str = ".",
        cancel_event: asyncio.Event | None = None,
    ) -> list[DirectoryItem]:
        """
        列出目录内容

        Args:
            directory_path: 目录路径
            cancel_event: 取消事件，设置后可中断等待

        Returns:
            目录项列表
        """
        try:
            safe_path = self._resolve_path(directory_path)
        except ValueError:
            return []

        # detail=True 必须设置，以获取文件类型信息
        result = await self.pool.call(
            self.meta_url, Operation.LISTDIR, safe_path, True,
            cancel_event=cancel_event,
        )

        items = []
        for entry in result.entries:
            # detail=True 时返回 FileInfo 对象
            if isinstance(entry, FileInfo):
                item_type = "directory" if stat.S_ISDIR(entry.st_mode) else "file"
                items.append(DirectoryItem(name=entry.name, type=item_type))

        # 排序：目录优先，然后按名称排序
        items.sort(key=lambda x: (x.type != "directory", x.name))
        return items

    # ========== 删除操作 ==========

    async def delete_item(
        self, path: str,
        cancel_event: asyncio.Event | None = None,
    ) -> OperationResult:
        """
        删除文件或目录

        Args:
            path: 要删除的路径
            cancel_event: 取消事件，设置后可中断等待

        Returns:
            操作结果
        """
        item_type = await self.get_item_type(path, cancel_event=cancel_event)
        if item_type is None:
            return OperationResult(
                success=False,
                item_type="file",
                source_path=path,
                message=f"路径不存在：{path}"
            )

        safe_path = self._resolve_path(path)
        await self.pool.call(
            self.meta_url, Operation.RMR, safe_path,
            cancel_event=cancel_event,
        )

        type_name = "目录" if item_type == "directory" else "文件"
        return OperationResult(
            success=True,
            item_type=item_type,
            source_path=path,
            message=f"成功删除{type_name}：{path}"
        )

    # ========== 移动操作 ==========

    async def move_item(
        self,
        source_path: str,
        destination_path: str,
        cancel_event: asyncio.Event | None = None,
    ) -> OperationResult:
        """
        移动/重命名文件或目录

        Args:
            source_path: 源路径
            destination_path: 目标路径
            cancel_event: 取消事件，设置后可中断等待

        Returns:
            操作结果

        Raises:
            FileNotFoundError: 源路径不存在
            FileExistsError: 目标路径已存在
        """
        item_type = await self.get_item_type(source_path, cancel_event=cancel_event)
        if item_type is None:
            raise FileNotFoundError(f"源路径不存在：{source_path}")

        dest_type = await self.get_item_type(destination_path, cancel_event=cancel_event)
        if dest_type is not None:
            raise FileExistsError(f"目标路径已存在：{destination_path}")

        src_safe = self._resolve_path(source_path)
        dst_safe = self._resolve_path(destination_path)

        await self.pool.call(
            self.meta_url, Operation.RENAME, src_safe, dst_safe,
            cancel_event=cancel_event,
        )

        type_name = "目录" if item_type == "directory" else "文件"
        return OperationResult(
            success=True,
            item_type=item_type,
            source_path=source_path,
            destination_path=destination_path,
            message=f"成功移动{type_name}：{source_path} -> {destination_path}"
        )

    # ========== 复制操作 ==========

    async def copy_item(
        self,
        source_path: str,
        destination_path: str,
        cancel_event: asyncio.Event | None = None,
    ) -> OperationResult:
        """
        复制文件或目录

        Args:
            source_path: 源路径
            destination_path: 目标路径
            cancel_event: 取消事件，设置后可中断等待

        Returns:
            操作结果

        Raises:
            FileNotFoundError: 源路径不存在
            FileExistsError: 目标路径已存在
        """
        item_type = await self.get_item_type(source_path, cancel_event=cancel_event)
        if item_type is None:
            raise FileNotFoundError(f"源路径不存在：{source_path}")

        dest_type = await self.get_item_type(destination_path, cancel_event=cancel_event)
        if dest_type is not None:
            raise FileExistsError(f"目标路径已存在：{destination_path}")

        src_safe = self._resolve_path(source_path)
        dst_safe = self._resolve_path(destination_path)

        await self.pool.call(
            self.meta_url, Operation.CLONE, src_safe, dst_safe,
            cancel_event=cancel_event,
        )

        type_name = "目录" if item_type == "directory" else "文件"
        return OperationResult(
            success=True,
            item_type=item_type,
            source_path=source_path,
            destination_path=destination_path,
            message=f"成功复制{type_name}：{source_path} -> {destination_path}"
        )