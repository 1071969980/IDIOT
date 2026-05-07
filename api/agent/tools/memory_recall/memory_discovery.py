"""记忆索引文件发现辅助函数（memory_recall 专用）

从允许的相对路径集合中，发现 /dist_fs/sys/memory/ 下的 MEMORY.md 文件，
返回目录路径和文件内容，供 context 注入钩子使用。
"""

from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from uuid import UUID

from api.agent.tools.file_operations.storage_backend.juicefs_sdk import JuiceFSSdkBackend

if TYPE_CHECKING:
    pass


def _get_juicefs_backend(
    session_id: UUID,
    user_id: UUID,
    allowed_rel_dirs: set[PurePosixPath],
) -> JuiceFSSdkBackend:
    """构造 JuiceFSSdkBackend 实例。"""
    return JuiceFSSdkBackend(
        session_id=session_id,
        user_id=user_id,
        allowed_rel_dirs_in_juicefs_for_tool=list(allowed_rel_dirs),
    )


async def discover_memory_index_files(
    allowed_rel_dirs: set[PurePosixPath],
    session_id: UUID,
    user_id: UUID,
) -> list[tuple[str, str]]:
    """发现 /dist_fs/sys/memory/ 子路径下的 MEMORY.md 文件。

    Returns:
        list[tuple[str, str]]: 每个元素为 (directory_path, memory_md_content)。
        directory_path 为 MEMORY.md 所在目录的绝对路径，
        例如 "/dist_fs/sys/memory/global"。
    """
    memory_root = PurePosixPath("/dist_fs/sys/memory")
    backend = _get_juicefs_backend(session_id, user_id, allowed_rel_dirs)
    found: list[tuple[str, str]] = []
    for rel_dir in allowed_rel_dirs:
        abs_path = PurePosixPath("/dist_fs") / rel_dir
        try:
            abs_path.relative_to(memory_root)
        except ValueError:
            continue
        memory_md_path = abs_path / "MEMORY.md"
        if await backend.file_exists(str(memory_md_path)):
            content, _, _ = await backend.read_file(str(memory_md_path))
            found.append((str(abs_path), content))
    return found
