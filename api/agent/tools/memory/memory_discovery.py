"""记忆索引文件发现辅助函数

从 memory_dirs 中发现 /dist_fs/sys/memory/ 下的 MEMORY.md 文件，
返回目录路径和文件内容，供 recall/write 的 context 注入钩子使用。
"""

from pathlib import PurePosixPath
from uuid import UUID

from api.agent.tools.file_operations.config_scope_data_model import FileOpsToolScope
from api.agent.tools.file_operations.storage_backend.juicefs_sdk import JuiceFSSdkBackend


def _get_juicefs_backend(
    session_id: UUID,
    scope: FileOpsToolScope,
) -> JuiceFSSdkBackend:
    """构造 JuiceFSSdkBackend 实例。"""
    return JuiceFSSdkBackend(
        session_id=session_id,
        scope=scope,
    )


async def discover_memory_index_files(
    memory_dirs: list[PurePosixPath],
    session_id: UUID,
    scope: FileOpsToolScope,
) -> list[tuple[str, str]]:
    """发现 /dist_fs/sys/memory/ 子路径下的 MEMORY.md 文件。

    Args:
        memory_dirs: 记忆目录相对路径列表。
        session_id: 会话 ID。
        scope: 文件操作作用域。

    Returns:
        list[tuple[str, str]]: 每个元素为
        (directory_path, memory_md_content)。
    """
    backend = _get_juicefs_backend(session_id, scope)
    found: list[tuple[str, str]] = []
    for rel_dir in memory_dirs:
        abs_path = PurePosixPath("/dist_fs") / rel_dir
        memory_md_path = abs_path / "MEMORY.md"
        if await backend.file_exists(str(memory_md_path)):
            content, _, _ = await backend.read_file(
                str(memory_md_path),
            )
            found.append((str(abs_path), content))
    return found
