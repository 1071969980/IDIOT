---
文档标题：agent_lifecycle_decorator_spec_testing_manual
文档描述：描述 AgentBase 生命周期装饰器系统的手动验证测试建议。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [手动验证](#手动验证)

---

### 手动验证

#### 1. 签名验证测试

创建测试文件 `test_manual_validation.py`：

```python
from api.agent.life_cycle_decorators import lifecycle_hook

# 应该抛出 SignatureMismatchError
try:
    @lifecycle_hook('on_generate_delta')
    async def wrong_signature(self, wrong_param: int):
        pass
    print("❌ 签名验证失败：应该检测到参数不匹配")
except Exception as e:
    print(f"✓ 签名验证正确：{e}")

# 应该成功
@lifecycle_hook('on_generate_delta')
async def correct_signature(self, delta: str):
    pass
print("✓ 正确签名通过验证")
```

#### 2. 基本功能测试

```python
import asyncio
from api.agent.base_agent import AgentBase
from api.agent.life_cycle_decorators import lifecycle_hook, agent_decorator

@lifecycle_hook('on_generate_delta')
async def log_delta(self, delta: str):
    print(f"Delta received: {delta}")

@agent_decorator(log_delta)
class TestAgent(AgentBase):
    pass

async def main():
    agent = TestAgent(
        cancel_event=asyncio.Event(),
        tools=[],
        tool_call_function={}
    )
    await agent.on_generate_delta("test")
    print("✓ 基本功能测试通过")

asyncio.run(main())
```

#### 3. 执行顺序测试

```python
import asyncio
from api.agent.base_agent import AgentBase
from api.agent.life_cycle_decorators import lifecycle_hook, agent_decorator

execution_log = []

@lifecycle_hook('on_agent_start')
async def hook1(self, memories):
    execution_log.append('hook1')

@lifecycle_hook('on_agent_start')
async def hook2(self, memories):
    execution_log.append('hook2')

@lifecycle_hook('on_agent_start')
async def hook3(self, memories):
    execution_log.append('hook3')

@agent_decorator(hook1, hook2, hook3)
class TestAgent(AgentBase):
    pass

async def main():
    agent = TestAgent(
        cancel_event=asyncio.Event(),
        tools=[],
        tool_call_function={}
    )
    await agent.on_agent_start([])

    expected = ['hook1', 'hook2', 'hook3']
    if execution_log == expected:
        print(f"✓ 执行顺序正确：{execution_log}")
    else:
        print(f"❌ 执行顺序错误：期望 {expected}，实际 {execution_log}")

asyncio.run(main())
```

#### 4. 返回值修改测试

```python
import asyncio
from api.agent.base_agent import AgentBase
from api.agent.life_cycle_decorators import lifecycle_hook, agent_decorator

@lifecycle_hook('prepare_kwargs', modifies_return=True)
async def add_custom_param(self, base_kwargs: dict, thinking: bool):
    base_kwargs['custom_param'] = 'custom_value'
    return base_kwargs

@agent_decorator(add_custom_param)
class TestAgent(AgentBase):
    pass

async def main():
    agent = TestAgent(
        cancel_event=asyncio.Event(),
        tools=[],
        tool_call_function={}
    )
    kwargs = await agent.prepare_kwargs(True)
    print(f"kwargs: {kwargs}")
    assert 'custom_param' in kwargs
    assert kwargs['custom_param'] == 'custom_value'
    print("✓ 返回值修改正确")

asyncio.run(main())
```

---

## 相关文件

- [审核目标](./01_review_goals.md)
- [测试建议 - 单元测试与集成测试](./02_testing_unit_integration.md)
- [验收标准与风险](./04_acceptance_and_risks.md)
- [上下文文档](../agent_lifecycle_decorator_spec_context.md)
- [设计文档](../agent_lifecycle_decorator_spec_design.md)
- [实现文档](../agent_lifecycle_decorator_spec_implementation.md)
