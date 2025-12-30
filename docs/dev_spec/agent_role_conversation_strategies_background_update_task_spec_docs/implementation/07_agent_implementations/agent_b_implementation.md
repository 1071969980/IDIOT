# Agent B：更新对话总结指导文件

---
文档标题：agent_b_implementation
文档描述：Agent B 负责根据 Agent A 更新后的对话策略，更新对话总结指导文件。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [Agent B：更新对话总结指导文件](#agent-b更新对话总结指导文件)
    - [文件路径](#文件路径)
    - [执行流程](#执行流程)
    - [工具定义](#工具定义)
    - [实现要点](#实现要点)

## Agent B：更新对话总结指导文件

### 文件路径

`background_update/agents/agent_b_update_guidance.py`

### 执行流程

1. 获取并编译 Langfuse 提示词模板
2. 构造两个动态工具：`read_guidance_part` 和 `edit_guidance`
3. 构造 OpenAI 格式的记忆（memories）
4. 初始化 AgentBase
5. 执行 Agent（带重试逻辑）
6. 检查工具调用状态

[查看完整实现代码](../examples/agent_b_complete.py)

### 工具定义

**工具1: read_guidance_part**
- 读取对话总结指导文件的部分内容
- 参数：`offset`（起始行号），`limit`（读取的行数）
- 帮助 AI 了解当前指导的具体内容

**工具2: edit_guidance**
- 编辑对话总结指导的内容
- 参数：`old_text`（要替换的原始文本），`new_text`（替换后的新文本），`replace_all`（是否替换所有出现）
- 执行实际的文本编辑操作

### 实现要点

1. **提示词获取**：
   - 使用 `_get_prompt_from_langfuse("agent-role-update/update-conclusion-guidance")`
   - 注意：这是同步函数，不需要 `await`

2. **提示词编译**：
   ```python
   system_prompt = prompt.compile(
       updated_strategies=updated_strategies,
       original_guidance=original_guidance,
       review_suggestions=review_suggestions or ""
   )
   ```

3. **依赖 Agent A 的结果**：
   - `updated_strategies` 参数来自 Agent A 的执行结果
   - 确保指导内容与更新后的策略保持一致

4. **重试逻辑**：
   - 最多重试 3 次
   - 每次重试前重置工作容器
   - 检查 `agent_b_result["tool_called"]` 判断是否成功

5. **无返回值**：
   - 函数返回 `None`
   - 结果通过修改外部容器传递

## 相关实现文档

- [可用的代码基础设施](../01_code_infrastructure.md)
- [文件夹结构设计](../02_folder_structure.md)
- [外部容器管理策略](../06_container_management.md)
- [Agent A 实现](./agent_a_implementation.md)
- [Agent C 实现](./agent_c_implementation.md)
