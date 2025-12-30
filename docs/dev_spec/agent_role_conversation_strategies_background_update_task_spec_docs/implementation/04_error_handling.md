# 角色对话策略更新功能 - 错误处理规范

---
文档标题：background_update_task_spec_implementation
文档描述：本文档描述角色对话策略更新功能的错误处理规范，包括可用的异常类型、错误处理策略、异常处理的关键原则和代码模式。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [错误处理规范](#错误处理规范)
    - [可用的异常类型](#可用的异常类型)
    - [错误处理策略](#错误处理策略)
    - [异常处理的关键原则](#异常处理的关键原则)

## 错误处理规范

### 可用的异常类型

来自 `../../../../api/user_space/file_system/fs_utils/file_object.py`:

- `HybridFileNotFoundError`: 文件不存在或路径不是文件
- `InvalidFileModeError`: 不支持的文件模式
- `LockAcquisitionError`: 无法获取分布式锁
- `S3OperationError`: S3 操作失败（上传/下载）
- `DatabaseOperationError`: 数据库操作失败
- `HybridFileSystemError`: 基础文件系统异常

### 错误处理策略

**任务失败或超时**:
- 确保所有用户空间文件没有进行意外更改
- 不进行重试
- 记录错误日志（使用 logfire.error）
- 如果是第二阶段之后失败，需要将读取到的 `update_cache` 回写到缓存文件

**内存操作失败**:

1. **读取文件失败**（第二阶段）：
   - 捕获异常，不向上抛出
   - 记录 logfire.error，包含文件路径、异常类型和异常信息
   - 区分异常原因：
     - `HybridFileNotFoundError`: 文件不存在，任务终止，**无需回滚**（缓存文件未被修改）
     - `LockAcquisitionError`: 无法获取文件锁，任务终止，**无需回滚**
     - `S3OperationError`: S3 下载失败，任务终止，**无需回滚**
     - `DatabaseOperationError`: 数据库查询失败，任务终止，**无需回滚**
     - 其他异常：记录详细信息，任务终止，**无需回滚**
   - **关键**: 此时 `update_cache` 未成功读取或缓存文件未被清空，因此不执行回滚操作

2. **写入文件失败**（第三阶段审查通过后）：
   - 捕获异常，不向上抛出
   - 记录 logfire.error，包含文件路径、异常类型和异常信息
   - 尝试将读取到的 `update_cache` 回写到缓存文件
   - **回滚操作必须用 try-except 包裹**：
     - 如果回滚也失败，记录 logfire.warning，包含回滚失败的异常信息
     - **绝不重新抛出回滚异常**，避免掩盖原始写入失败异常
   - 任务终止

**Agent 执行失败**:

1. **Agent 未调用工具**：
   - 根据状态控制逻辑重新执行（最多 3 次）
   - 超过最大重试次数后，任务终止
   - 记录 logfire.warning
   - 尝试回滚缓存文件（回滚操作必须用 try-except 包裹）

2. **Agent 输出格式错误**：
   - 捕获异常，记录 logfire.error
   - 任务终止
   - 尝试回滚缓存文件（回滚操作必须用 try-except 包裹）

### 异常处理的关键原则

1. **所有 catch/finally 块中的操作都必须用 try-except 包裹**
2. **回滚操作失败绝不抛出异常**，只记录日志
3. **避免掩盖原始异常**：回滚失败时，原始异常信息仍然是主要的
4. **区分异常原因**：根据不同异常类型采取不同的处理策略
5. **确保任务终止**：任何情况下都不向上抛出异常
6. **文件不存在时不需要回滚**：如果原始异常是 `HybridFileNotFoundError`，说明缓存文件未被修改

### 异常处理代码模式

[查看完整的异常处理代码模式](./examples/error_handling_pattern.py)

**关键代码片段**:

```python
from api.user_space.file_system.fs_utils.exception import (
    HybridFileNotFoundError,
    LockAcquisitionError,
    S3OperationError,
    DatabaseOperationError,
)

# 第二阶段：准备文件内容
try:
    # ========== 在同一个分布式锁内完成缓存文件的读取、提取、格式化、清空 ==========
    async with user_agent_role_strategies_update_cache_file(user_id, role_name, "r+") as f:
        cache_content = f.read().decode("utf-8")
        update_cache = ujson.loads(cache_content) if cache_content else {}
        original_update_cache = update_cache.copy()  # 保存原始内容

        # 提取更新列表
        strategies_list = update_cache.get("strategies_update_cache", [])

        # 检查退出条件
        if not strategies_list:
            logfire.info("agent-role-update::no_updates_pending")
            return  # 没有待处理的更新，正常结束

        # 格式化 strategies_list 为易读文本（在锁内完成，但操作很快）
        formatted_items = []
        for i, item in enumerate(strategies_list, 1):
            formatted_items.append(
                f"## 更新请求 {i}\n\n"
                f"**更新内容**:\n{item['update_content']}\n\n"
                f"**相关上下文**:\n{item['context']}"
            )
        strategies_update_list = "\n\n".join(formatted_items)

        # 清空 strategies_update_cache 数组（保留其他 JSON 结构）
        update_cache["strategies_update_cache"] = []

        # 将更新后的缓存写回文件（在同一锁内，确保原子性）
        f.seek(0)  # 回到文件开头
        f.write(ujson.dumps(update_cache).encode("utf-8"))
        f.truncate()  # 截断文件，移除旧内容
        cache_modified = True

except HybridFileNotFoundError as e:
    logfire.error("agent-role-update::file_not_found",
                 file_path=str(e.file_path) if hasattr(e, 'file_path') else "unknown",
                 error_type="HybridFileNotFoundError",
                 error_message=str(e))
    return  # 文件不存在，缓存未被修改，无需回滚

except LockAcquisitionError as e:
    logfire.error("agent-role-update::lock_acquisition_failed",
                 error_type="LockAcquisitionError",
                 error_message=str(e))
    return  # 无法获取锁，缓存未被修改，无需回滚

except (S3OperationError, DatabaseOperationError) as e:
    logfire.error("agent-role-update::file_operation_failed",
                 error_type=type(e).__name__,
                 error_message=str(e))
    return  # 文件操作失败，缓存未被修改或读取未完成，无需回滚

except Exception as e:
    logfire.error("agent-role-update::unexpected_read_error",
                 error_type=type(e).__name__,
                 error_message=str(e))
    return  # 其他异常，保守处理，无需回滚
```

## 相关实现文档

- [可用的代码基础设施](./01_code_infrastructure.md)
- [文件夹结构设计](./02_folder_structure.md)
- [任务触发规范](./03_task_triggering.md)
- [日志记录规范](./05_logging.md)
- [外部容器管理策略](./06_container_management.md)
- [Agent 实现示例](./07_agent_implementations/)
- [上下文文档](../background_update_task_spec_context.md)
- [设计文档](../background_update_task_spec_design.md)
