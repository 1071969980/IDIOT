# Agent C：审查更新结果

---
文档标题：agent_c_implementation
文档描述：Agent C 负责审查 Agent A 和 Agent B 的更新结果，给出评分和修改建议。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [Agent C：审查更新结果](#agent-c审查更新结果)
    - [文件路径](#文件路径)
    - [执行流程](#执行流程)
    - [Diff 生成](#diff-生成)
    - [工具定义](#工具定义)
    - [实现要点](#实现要点)

## Agent C：审查更新结果

### 文件路径

`background_update/agents/agent_c_review.py`

### 执行流程

1. 生成 `strategies_diff` 和 `guidance_diff`
2. 获取并编译 Langfuse 提示词模板
3. 构造动态工具：`submit_review_result`
4. 构造 OpenAI 格式的记忆（memories）
5. 初始化 AgentBase
6. 执行 Agent（不需要重试，只执行一次）

[查看完整实现代码](../examples/agent_c_complete.py)

### Diff 生成

使用 Python 标准库 `difflib` 生成 unified diff 格式：

```python
import difflib

def generate_diff(original: str, updated: str, filename: str = "file") -> str:
    """生成 unified diff 格式"""
    original_lines = original.splitlines(keepends=True)
    updated_lines = updated.splitlines(keepends=True)
    diff = difflib.unified_diff(
        original_lines,
        updated_lines,
        fromfile=f"Original {filename}",
        tofile=f"Updated {filename}",
        lineterm=""
    )
    return "".join(diff)
```

### 工具定义

**工具: submit_review_result**
- 提交对更新内容的审查结果
- 参数：`score`（0-100 分的评分），`suggestions`（修改建议）
- 根据 diff 评估更新的质量

### 实现要点

1. **提示词获取**：
   - 使用 `_get_prompt_from_langfuse("agent-role-update/review-updates")`
   - 注意：这是同步函数，不需要 `await`

2. **提示词编译**：
   ```python
   system_prompt = prompt.compile(
       strategies_diff=strategies_diff,
       guidance_diff=guidance_diff
   )
   ```

3. **审查标准**：
   - 更新是否准确反映了用户的请求
   - 内容是否连贯一致
   - 格式是否规范
   - 是否存在遗漏或错误

4. **评分标准**：
   - 80-100 分：优秀，可以通过
   - 60-79 分：良好，但需要修改
   - 0-59 分：不合格，需要重新修改

5. **无返回值**：
   - 函数返回 `None`
   - 审查结果通过工具闭包写入外部容器 `agent_c_result`

6. **不需要重试**：
   - Agent C 只执行一次
   - 审查结果直接作为最终结果

## 相关实现文档

- [可用的代码基础设施](../01_code_infrastructure.md)
- [文件夹结构设计](../02_folder_structure.md)
- [外部容器管理策略](../06_container_management.md)
- [Agent A 实现](./agent_a_implementation.md)
- [Agent B 实现](./agent_b_implementation.md)
