# Agent A：更新对话策略文件

---
文档标题：agent_a_implementation
文档描述：Agent A 负责根据用户的更新请求和审查建议，更新对话策略文件。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [Agent A：更新对话策略文件](#agent-a更新对话策略文件)
    - [文件路径](#文件路径)
    - [执行流程](#执行流程)
    - [工具定义](#工具定义)
    - [实现要点](#实现要点)

## Agent A：更新对话策略文件

### 文件路径

`background_update/agents/agent_a_update_strategies.py`

### 执行流程

1. 获取并编译 Langfuse 提示词模板
2. 构造两个动态工具：`read_strategies_part` 和 `edit_strategies`
3. 构造 OpenAI 格式的记忆（memories）
4. 初始化 AgentBase
5. 执行 Agent（带重试逻辑）
6. 检查工具调用状态

[查看完整实现代码](../examples/agent_a_complete.py)

### 工具定义

**工具1: read_strategies_part**
- 读取对话策略文件的部分内容
- 参数：`offset`（起始行号），`limit`（读取的行数）
- 帮助 AI 了解当前策略的具体内容

**工具2: edit_strategies**
- 编辑对话策略的内容
- 参数：`old_text`（要替换的原始文本），`new_text`（替换后的新文本），`replace_all`（是否替换所有出现）
- 执行实际的文本编辑操作

### 实现要点

1. **提示词获取**：
   - 使用 `_get_prompt_from_langfuse("agent-role-update/update-strategies")`
   - 注意：这是同步函数，不需要 `await`

2. **提示词编译**：
   ```python
   system_prompt = prompt.compile(
       original_strategies=original_strategies,
       strategies_update_cache=strategies_update_list,
       review_suggestions=review_suggestions or ""
   )
   ```

3. **工具闭包捕获**：
   - 工具回调函数通过闭包捕获外部容器 `agent_a_working_strategies` 和 `agent_a_result`
   - 直接修改可变容器的内容

4. **重试逻辑**：
   - 最多重试 3 次
   - 每次重试前重置工作容器
   - 检查 `agent_a_result["tool_called"]` 判断是否成功

5. **无返回值**：
   - 函数返回 `None`
   - 结果通过修改外部容器传递

## 相关实现文档

- [可用的代码基础设施](../01_code_infrastructure.md)
- [文件夹结构设计](../02_folder_structure.md)
- [外部容器管理策略](../06_container_management.md)
- [Agent B 实现](./agent_b_implementation.md)
- [Agent C 实现](./agent_c_implementation.md)
