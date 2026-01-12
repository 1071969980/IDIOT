# 角色对话策略更新功能 - 任务触发规范

---
文档标题：background_update_task_spec_implementation
文档描述：本文档描述角色对话策略更新功能的任务触发规范，包括在 constructor.py 中的集成和在 task_runner.py 中的完整实现。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [任务触发规范](#任务触发规范)
    - [在 constructor.py 中的集成](#在-constructorpy-中的集成)
    - [在 task_runner.py 中的完整实现](#在-task_runnerpy-中的完整实现)

## 任务触发规范

### 在 `constructor.py` 中的集成

在现有工具的 `__call__` 方法中，写入缓存成功后，立即发起后台更新任务。

[查看 constructor.py 集成代码示例](./examples/constructor_integration.py)

**关键代码片段**:
```python
# 写入缓存成功后，立即发起后台更新任务
from api.agent.tools.agent_roles.update_role_conversation_strategies.background_update.task_runner import run_background_update_task

task = asyncio.create_task(
    run_background_update_task(
        user_id=self.user_id,
        role_name=param.role_name
    )
)

# 返回成功消息（不等待任务完成）
return ToolTaskResult(
    str_content="更新任务已提交，后台将自动处理。"
)
```

**注意事项**:
- 使用 `asyncio.create_task()` 创建后台任务，不使用 `await` 等待
- 任务立即返回，不阻塞用户交互
- 后台任务的异常不会影响主流程（后台任务会自己记录日志）

### 在 `task_runner.py` 中的完整实现

[查看 task_runner.py 完整实现示例](./examples/task_runner_implementation.py)

**关键设计要点**:

1. **信号发布时机**：在任务启动的最开始（第一阶段之前）
2. **信号作用**：终止其他正在第一阶段等待的旧任务
3. **第一阶段返回值**：
   - `True`（超时）：没有新任务来抢占，继续执行
   - `False`（收到信号）：有更新的任务启动，当前任务退出
4. **异常处理**：所有异常都被捕获并记录，不会向上传播

**执行流程**:
```
0. 任务启动前：发布 planning 信号（终止其他等待的任务）
   ↓
1. 第一阶段：计划更新任务（等待 30 秒）
   ↓
2. 第二阶段：准备文件内容
   ↓
3. 第三阶段：更新任务（Agent 循环）
```

## 相关实现文档

- [可用的代码基础设施](./01_code_infrastructure.md)
- [文件夹结构设计](./02_folder_structure.md)
- [错误处理规范](./04_error_handling.md)
- [日志记录规范](./05_logging.md)
- [外部容器管理策略](./06_container_management.md)
- [Agent 实现示例](./07_agent_implementations/)
- [上下文文档](../background_update_task_spec_context.md)
- [设计文档](../background_update_task_spec_design.md)
