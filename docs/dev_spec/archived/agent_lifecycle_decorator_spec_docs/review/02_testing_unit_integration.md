---
文档标题：agent_lifecycle_decorator_spec_testing_unit_integration
文档描述：描述 AgentBase 生命周期装饰器系统的单元测试和集成测试建议。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [单元测试](#单元测试)
- [集成测试](#集成测试)

---

## 单元测试

#### 1. 签名验证测试

**测试文件**：`testcase/api/agent/test_life_cycle_decorators/test_signature_validator.py`

```python
import pytest
from api.agent.life_cycle_decorators.signature_validator import (
    LifecycleSignatureValidator,
    SignatureMismatchError
)

def test_validate_async_method_correct_signature():
    """测试正确签名的异步方法验证"""
    validator = LifecycleSignatureValidator()

    async def correct_hook(self, delta: str):
        pass

    # 不应该抛出异常
    validator.validate('on_generate_delta', correct_hook, modifies_return=False)


def test_validate_async_method_wrong_parameter_count():
    """测试参数个数不匹配"""
    validator = LifecycleSignatureValidator()

    async def wrong_hook(self, delta: str, extra: int):
        pass

    with pytest.raises(SignatureMismatchError):
        validator.validate('on_generate_delta', wrong_hook, modifies_return=False)


def test_validate_async_sync_mismatch():
    """测试异步/同步不匹配"""
    validator = LifecycleSignatureValidator()

    def sync_hook(self, delta: str):  # 应该是 async
        pass

    with pytest.raises(SignatureMismatchError):
        validator.validate('on_generate_delta', sync_hook, modifies_return=False)


def test_validate_modifies_return_correct_signature():
    """测试 modifies_return=True 的正确签名"""
    validator = LifecycleSignatureValidator()

    async def correct_hook(self, base_kwargs: dict, thinking: bool):
        return base_kwargs

    # 不应该抛出异常
    validator.validate('prepare_kwargs', correct_hook, modifies_return=True)


def test_validate_modifies_return_missing_return_param():
    """测试 modifies_return=True 时缺少返回值参数"""
    validator = LifecycleSignatureValidator()

    async def wrong_hook(self, thinking: bool):  # 少了 base_kwargs
        return {}

    with pytest.raises(SignatureMismatchError):
        validator.validate('prepare_kwargs', wrong_hook, modifies_return=True)
```

#### 2. 方法组合测试

**测试文件**：`testcase/api/agent/test_life_cycle_decorators/test_composer.py`

```python
import pytest
import asyncio
from api.agent.life_cycle_decorators.composer import MethodComposer

@pytest.mark.asyncio
async def test_compose_async():
    """测试异步方法组合"""
    composer = MethodComposer()

    execution_log = []

    async def base_method(self, value):
        execution_log.append('base')
        return value * 2

    async def wrapper(self, value):
        execution_log.append('wrapper')

    composed = composer.compose_async(base_method, wrapper)
    result = await composed(None, 5)

    assert execution_log == ['wrapper', 'base']
    assert result == 10


@pytest.mark.asyncio
async def test_compose_async_with_return():
    """测试异步方法组合（修改返回值）"""
    composer = MethodComposer()

    async def base_method(self, value):
        return value * 2

    async def wrapper(self, base_result, value):
        return base_result + 10

    composed = composer.compose_async_with_return(base_method, wrapper)
    result = await composed(None, 5)

    assert result == 20  # (5 * 2) + 10


def test_compose_sync():
    """测试同步方法组合"""
    composer = MethodComposer()

    execution_log = []

    def base_method(self, value):
        execution_log.append('base')
        return value * 2

    def wrapper(self, value):
        execution_log.append('wrapper')

    composed = composer.compose_sync(base_method, wrapper)
    result = composed(None, 5)

    assert execution_log == ['wrapper', 'base']
    assert result == 10


def test_compose_sync_with_return():
    """测试同步方法组合（修改返回值）"""
    composer = MethodComposer()

    def base_method(self, value):
        return value * 2

    def wrapper(self, base_result, value):
        return base_result + 10

    composed = composer.compose_sync_with_return(base_method, wrapper)
    result = composed(None, 5)

    assert result == 20
```

#### 3. 装饰器工厂测试

**测试文件**：`testcase/api/agent/test_life_cycle_decorators/test_factory.py`

```python
import pytest
import asyncio
from api.agent.base_agent import AgentBase
from api.agent.life_cycle_decorators.factory import lifecycle_hook, agent_decorator
from openai.types.chat import ChatCompletionMessageParam

@pytest.mark.asyncio
async def test_lifecycle_hook_creates_metadata():
    """测试 lifecycle_hook 创建元数据"""
    @lifecycle_hook('on_generate_delta')
    async def my_hook(self, delta: str):
        pass

    assert hasattr(my_hook, '_lifecycle_hook')
    assert my_hook._lifecycle_hook.method_name == 'on_generate_delta'
    assert my_hook._lifecycle_hook.modifies_return is False


@pytest.mark.asyncio
async def test_agent_decorator_applies_hooks():
    """测试 agent_decorator 应用钩子"""
    execution_log = []

    @lifecycle_hook('on_generate_delta')
    async def log_hook(self, delta: str):
        execution_log.append(f'hook: {delta}')

    @agent_decorator(log_hook)
    class TestAgent(AgentBase):
        async def on_generate_delta(self, delta: str):
            execution_log.append(f'method: {delta}')

    agent = TestAgent(
        cancel_event=asyncio.Event(),
        tools=[],
        tool_call_function={}
    )

    await agent.on_generate_delta('test')

    assert execution_log == ['hook: test', 'method: test']


@pytest.mark.asyncio
async def test_multiple_hooks_execution_order():
    """测试多个钩子按顺序执行"""
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

    agent = TestAgent(
        cancel_event=asyncio.Event(),
        tools=[],
        tool_call_function={}
    )

    await agent.on_agent_start([])

    assert execution_log == ['hook1', 'hook2', 'hook3']


@pytest.mark.asyncio
async def test_modifies_return():
    """测试修改返回值"""
    @lifecycle_hook('prepare_kwargs', modifies_return=True)
    async def add_custom_kwarg(self, base_kwargs: dict, thinking: bool):
        base_kwargs['custom'] = 'value'
        return base_kwargs

    @agent_decorator(add_custom_kwarg)
    class TestAgent(AgentBase):
        pass

    agent = TestAgent(
        cancel_event=asyncio.Event(),
        tools=[],
        tool_call_function={}
    )

    kwargs = await agent.prepare_kwargs(True)

    assert 'custom' in kwargs
    assert kwargs['custom'] == 'value'
    assert 'stream_options' in kwargs  # 原方法的 kwargs 还在
```

---

## 集成测试

#### 测试文件

**测试文件**：`testcase/api/agent/test_life_cycle_decorators/test_integration.py`

```python
import pytest
import asyncio
from api.agent.base_agent import AgentBase
from api.agent.life_cycle_decorators import lifecycle_hook, agent_decorator
from openai.types.chat import ChatCompletionMessageParam

@pytest.mark.asyncio
async def test_decorated_agent_full_lifecycle():
    """测试装饰器 agent 的完整生命周期"""

    metrics = {
        'deltas': [],
        'iterations': 0,
        'start_called': False,
        'complete_called': False,
    }

    @lifecycle_hook('on_agent_start')
    async def track_start(self, memories):
        metrics['start_called'] = True

    @lifecycle_hook('on_iteration_start')
    async def track_iteration(self, iteration: int):
        metrics['iterations'] = iteration

    @lifecycle_hook('on_generate_delta')
    async def track_delta(self, delta: str):
        metrics['deltas'].append(delta)

    @lifecycle_hook('on_agent_complete')
    async def track_complete(self):
        metrics['complete_called'] = True

    @agent_decorator(track_start, track_iteration, track_delta, track_complete)
    class TrackedAgent(AgentBase):
        pass

    agent = TrackedAgent(
        cancel_event=asyncio.Event(),
        tools=[],
        tool_call_function={}
    )

    # 模拟生命周期
    memories: list[ChatCompletionMessageParam] = []
    await agent.on_agent_start(memories)
    await agent.on_iteration_start(1)
    await agent.on_generate_start()
    await agent.on_generate_delta("Hello")
    await agent.on_generate_delta(" World")
    await agent.on_generate_complete("Hello World")
    await agent.on_iteration_end(1, memories)
    await agent.on_agent_complete()

    # 验证
    assert metrics['start_called'] is True
    assert metrics['iterations'] == 1
    assert metrics['deltas'] == ["Hello", " World"]
    assert metrics['complete_called'] is True


@pytest.mark.asyncio
async def test_mixed_inheritance_and_decorator():
    """测试继承和装饰器混合使用"""

    @lifecycle_hook('on_generate_delta')
    async def log_hook(self, delta: str):
        self.logs.append(f'hook: {delta}')

    @agent_decorator(log_hook)
    class CustomAgent(AgentBase):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.logs = []

        async def on_generate_delta(self, delta: str):
            self.logs.append(f'method: {delta}')

    agent = CustomAgent(
        cancel_event=asyncio.Event(),
        tools=[],
        tool_call_function={}
    )

    await agent.on_generate_delta('test')

    # 钩子先执行，然后是覆盖的方法
    assert agent.logs == ['hook: test', 'method: test']
```

---

## 相关文件

- [审核目标](./01_review_goals.md)
- [测试建议 - 手动验证](./03_testing_manual.md)
- [验收标准与风险](./04_acceptance_and_risks.md)
- [上下文文档](../agent_lifecycle_decorator_spec_context.md)
- [设计文档](../agent_lifecycle_decorator_spec_design.md)
- [实现文档](../agent_lifecycle_decorator_spec_implementation.md)
