---
文档标题：file_operations_tools_spec_design
文档描述：描述 Agent 文件操作工具（read_file, edit_file, write_file）的需求、概念设计和执行逻辑。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [设计概述](#设计概述)
- [工具设计](#工具设计)
    - [read_file 工具设计](#read_file-工具设计)
    - [edit_file 工具设计](#edit_file-工具设计)
    - [write_file 工具设计](#write_file-工具设计)
- [存储后端设计](#存储后端设计)
- [安全与并发设计](#安全与并发设计)
- [设计示例代码](#设计示例代码)

---

## 设计概述

本文档描述 read_file、edit_file、write_file 三个 Agent 文件操作工具的概念设计。三个工具共享统一的存储后端抽象接口，支持多种存储实现（内存、本地文件系统、用户空间文件系统）。

设计遵循以下原则：
- **存储后端抽象**: 业务逻辑与存储实现分离
- **配置驱动**: 通过配置选择存储后端
- **并发安全**: 利用用户空间文件系统的分布式锁
- **安全限制**: 用户空间后端禁止访问隐藏文件

详细设计请查看以下子文档。

## 工具设计

### read_file 工具设计

详细设计请查看：[design_docs/read_file_tool_design.md](design_docs/read_file_tool_design.md)

**功能概述**：读取文件内容，支持偏移量、行数限制和行号显示。

**核心参数**：
- `file_path`: 文件路径
- `offset`: 起始行偏移（可选）
- `limit`: 读取行数限制（可选）
- `show_line_numbers`: 是否显示行号（可选）

**输出格式**：带行号的内容字符串

### edit_file 工具设计

详细设计请查看：[design_docs/edit_file_tool_design.md](design_docs/edit_file_tool_design.md)

**功能概述**：编辑文件内容，通过替换指定字符串实现。

**核心参数**：
- `file_path`: 文件路径
- `old_string`: 要替换的字符串
- `new_string`: 替换后的字符串
- `replace_all`: 是否替换所有匹配项（可选，默认 false）

**重复检测**：如果 `old_string` 在文件中出现多次且 `replace_all=false`，返回错误提示用户。

### write_file 工具设计

详细设计请查看：[design_docs/write_file_tool_design.md](design_docs/write_file_tool_design.md)

**功能概述**：写入文件内容，支持创建新文件或覆盖现有文件。

**核心参数**：
- `file_path`: 文件路径
- `content`: 文件内容
- `mode`: 写入模式（可选，"create" 仅创建新文件，"overwrite" 允许覆盖）

## 存储后端设计

详细设计请查看：[design_docs/storage_backend_design.md](design_docs/storage_backend_design.md)

**抽象接口**：`FileOperationsStorageBackend` ABC

**三种存储后端**：

1. **MemoryFileBackend**（内存存储）
   - 使用类变量存储文件内容
   - `asyncio.Lock` 保护并发访问
   - 适合测试和短期使用

2. **LocalFileBackend**（本地文件系统）
   - 直接操作本地文件系统
   - 使用 `aiofiles` 进行异步文件操作
   - 适合测试环境

3. **UserSpaceFileBackend**（用户空间文件系统）
   - 集成 `HybridFileObject`
   - 自动分布式锁保护
   - 隐藏文件访问限制
   - 生产环境使用

**配置选择**：
```python
storage_backend: Literal["memory", "local", "user_space", "kwargs_DI"] = "memory"
```

## 安全与并发设计

详细设计请查看：[design_docs/security_concurrency_design.md](design_docs/security_concurrency_design.md)

**安全限制**：
- 隐藏文件检测：路径中任何以 `.` 开头的组件都被视为隐藏
- 路径验证：防止目录遍历攻击
- 仅 UserSpaceFileBackend 强制执行隐藏文件限制

**并发安全**：
- MemoryFileBackend: 使用 `asyncio.Lock`
- LocalFileBackend: 使用文件系统锁或 `asyncio.Lock`
- UserSpaceFileBackend: 使用 `RedisDistributedLock`（由 `HybridFileObject` 自动处理）

## 设计示例代码

设计阶段的示例代码请查看：[design_docs/examples/](design_docs/examples/)

- `read_file_example.py`: read_file 工具使用示例
- `edit_file_example.py`: edit_file 工具使用示例
